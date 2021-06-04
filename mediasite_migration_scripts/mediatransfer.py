import logging
import json
import os
import requests
import sys
from pathlib import Path
from functools import lru_cache

from mediasite_migration_scripts.ms_client.client import MediaServerClient
from mediasite_migration_scripts.utils import common as utils
from mediasite_migration_scripts.ms_client.client import MediaServerRequestError as MSReqErr
from mediasite_migration_scripts.video_compositor import VideoCompositor


logger = logging.getLogger(__name__)


class MediaTransfer():

    def __init__(self, config=dict(), mediasite_data=dict(), mediasite_users=dict(), unit_test=False, e2e_test=False, root_channel_oid=None):
        self.config = config
        self.e2e_test = e2e_test
        self.unit_test = unit_test
        self.redirections = dict()
        if self.unit_test:
            self.config['videos_format_allowed'] = {'video/mp4': True, "video/x-ms-wmv": False}
        else:
            self.ms_config = {'API_KEY': self.config.get('mediaserver_api_key', ''),
                              'CLIENT_ID': 'mediasite-migration-client',
                              'SERVER_URL': self.config.get('mediaserver_url', ''),
                              'VERIFY_SSL': False,
                              'LOG_LEVEL': 'WARNING',
                              'TIMEOUT': 120}
            self.ms_client = MediaServerClient(local_conf=self.ms_config, setup_logging=False)

            if root_channel_oid:
                self.root_channel = self.get_channel(root_channel_oid)
            else:
                self.root_channel = self.get_root_channel()

        self.formats_allowed = self.config.get('videos_formats_allowed', {})
        self.created_channels = dict()
        self.slide_annot_type = None
        self.chapters_annot_type = None
        self.public_paths = [folder.get('path', '') for folder in mediasite_data if len(folder.get('catalogs')) > 0]

        self.mediasite_data = mediasite_data
        self.mediasite_auth = (self.config.get('mediasite_api_user'), self.config.get('mediasite_api_password'))

        #self.users = self.to_mediaserver_users(mediasite_users)
        self.mediasite_userfolder = config.get('mediasite_userfolder', '/Mediasite Users/')

        self.mediaserver_data = self.to_mediaserver_keys()
        self.unknown_users_channel_title = config.get('mediaserver_unknown_users_channel_title', 'Mediasite Unknown Users')

        self.compositor = None
        self.composites_medias = list()
        self.download_folder = dl = Path(config.get('download_folder', ''))
        self.slides_folder = dl / 'slides'
        self.composites_folder = dl / 'composite'
        self.medias_folders = list()
        self.dl_session = None
        self.redirections_file = Path(config.get('redirections_file', 'redirections.json'))

    def write_redirections_file(self):
        if self.redirections:
            if self.redirections_file.is_file():
                logger.info(f'Reading existing redirections file {self.redirections_file}')
                with open(self.redirections_file, 'r') as f:
                    data = json.load(f)
                    logger.info('Updating redirections file')
                    data.update(self.redirections)
            else:
                data = self.redirections

            logger.info(f'Writing redirections file {self.redirections_file}')
            with open(self.redirections_file, 'w') as f:
                json.dump(data, f)

    def upload_medias(self, max_videos=None):
        logger.debug('Uploading videos')
        print(' ' * 50, end='\r')

        if max_videos:
            try:
                max_videos = int(max_videos)
                total_medias_uploaded = max_videos
            except Exception as e:
                logger.error(f'{max_videos} is not a valid number for videos maximum.')
                logger.debug(e)
        else:
            total_medias_uploaded = len(self.mediaserver_data)

        logger.debug(f'{total_medias_uploaded} medias found for uploading.')

        nb_medias_uploaded = 0
        attempts = 0
        while nb_medias_uploaded != total_medias_uploaded and attempts < 10:
            attempts += 1
            logger.debug(f'Attempt {attempts} for uploading medias.')
            if attempts > 1:
                nb_medias_left = total_medias_uploaded - nb_medias_uploaded
                logger.debug(f'{nb_medias_left} medias left to upload.')

            for index, media in enumerate(self.mediaserver_data):
                print(f'Uploading: [{nb_medias_uploaded} / {total_medias_uploaded}] -- {int(100 * (nb_medias_uploaded / total_medias_uploaded))}%', end='\r')

                if max_videos and index >= max_videos:
                    break

                if not media.get('ref', {}).get('media_oid'):
                    try:
                        data = media.get('data', {})  # mediaserver data
                        presentation_id = json.loads(data.get('external_data', {})).get('id')

                        channel_path = media['ref'].get('channel_path')
                        if channel_path.startswith(self.mediasite_userfolder):
                            if self.config.get('skip_userfolders'):
                                continue
                            target_channel = self.get_personal_channel_target(channel_path)
                        else:
                            channel_oid = self.create_channels(channel_path) or self.root_channel.get('oid')
                            target_channel = 'mscid-' + channel_oid

                        logger.debug(f'Will publish {presentation_id} into channel {target_channel}')
                        data['channel'] = target_channel

                        if data.get('video_type').startswith('composite_'):
                            if self.config.get('skip_composites'):
                                continue
                            logger.debug(f'Presentation {presentation_id} is a composite video.')

                            # do not provide url to MS, file will be treated locally, we'll add it later
                            data.pop('file_url', None)

                            # we store composites medias infos, to migrate them later
                            already_added = False
                            for v_composites in self.composites_medias:
                                if data.get('slug') == v_composites.get('data', {}).get('slug'):
                                    already_added = True
                                    break
                            if not already_added:
                                self.composites_medias.append(media)
                                nb_medias_uploaded += 1
                        else:
                            if self.config.get('skip_others'):
                                continue
                            existing_media = self.get_ms_media_by_ref(presentation_id)
                            if existing_media:
                                media_oid = existing_media['oid']
                                logger.warning(f'Presentation {presentation_id} already present on MediaServer (oid: {media_oid}), not reuploading')
                            else:
                                # store original presentation id to avoid duplicates
                                data['external_ref'] = presentation_id
                                result = self.ms_client.api('medias/add', method='post', data=data)
                                if result.get('success'):
                                    oid = result['oid']
                                    self.add_presentation_redirection(presentation_id, oid)
                                    media['ref']['media_oid'] = oid
                                    media['ref']['slug'] = result.get('slug')
                                    if data.get('api_key'):
                                        del data['api_key']

                                    self.migrate_slides(media)

                                    if data.get('video_type') == 'audio_only':
                                        thumb_ok = self._send_audio_thumb(media['ref']['media_oid'])
                                        if not thumb_ok:
                                            logger.warning('Failed to upload audio thumbail for audio presentation')

                                    if len(data.get('chapters')) > 0:
                                        self.add_chapters(media['ref']['media_oid'], chapters=data['chapters'])

                                    nb_medias_uploaded += 1
                                else:
                                    logger.error(f"Failed to upload media: {data['title']}")
                    except requests.exceptions.ReadTimeout:
                        logger.warning('Request timeout. Another attempt will be lauched at the end.')
                        continue

        if self.composites_medias:
            composite_ok = self.migrate_composites_videos()
            if composite_ok:
                logger.debug('Successfully migrate composites medias.')
            else:
                logger.error('Not all composite medias have been migrated.')

        print('')

        self.ms_client.session.close()
        if self.dl_session is not None:
            self.dl_session.close()

        return nb_medias_uploaded

    @lru_cache
    def get_personal_channel_target(self, channel_path):
        logger.debug(f'Get personal channel target for {channel_path}')
        #"/Mediasite Users/USERNAME/SUBFOLDER"
        target = ''
        subfolders = channel_path.split(self.mediasite_userfolder)[1].split('/')
        # ["USERNAME", "SUBFOLDER"]

        # mediaserver enforces lowercase usernames
        username = subfolders[0].lower()

        # mediaserver API cannot be queried by username
        user_id = self._get_user_id(username)

        if self._get_user_id(username):
            channel_oid = self.get_user_channel_oid(user_id=user_id)
            if len(subfolders) > 1:
                # Mediasite Users/USERNAME
                spath = self.mediasite_userfolder + subfolders[0] + '/'
                for s in subfolders[1:]:
                    spath += s + '/'
                    channel_oid = self._create_channel(channel_oid, s, True, spath)['oid']
            target = f'mscid-{channel_oid}'
        else:
            subfolders_path = "/".join(subfolders)
            target = f'mscpath-{self.unknown_users_channel_title}/{subfolders_path}'
        return target

    def get_ms_media_by_ref(self, external_ref):
        return self.search_by_external_ref(external_ref, object_type='media')

    def get_ms_channel_by_ref(self, external_ref):
        return self.search_by_external_ref(external_ref, object_type='channel')

    @lru_cache
    def search_by_external_ref(self, external_ref, object_type='channel'):
        data = {
            'search': external_ref,
            'fields': 'extref',
        }
        if object_type == 'channel':
            data['content'] = 'c'
            rkey = 'channels'
        elif object_type == 'media':
            data['content'] = 'v'
            rkey = 'videos'

        result = self.ms_client.api('search/', method='get', params=data)
        if result and result['success'] and result.get(rkey):
            # search does not return the external_ref, so lets take the first result
            return result[rkey][0]

    @lru_cache
    def _get_user_id(self, username):
        users = self.ms_client.api('users/', method='get', params={'search': username, 'search_in': 'username'})['users']
        # this is search, so multiple users may share username prefixes; find the exact match
        for user in users:
            if user['username'] == username:
                return user['id']

    def migrate_composites_videos(self):
        logger.info(f'Merging and migrating {len(self.composites_medias)} composite videos.')
        up_ok = False
        dl_ok = self.download_composites_videos()

        if dl_ok:
            logger.debug('Merging and uploading')
            nb_composites_medias_uploaded = 0
            for media in self.composites_medias:
                print(f'Uploading: [{nb_composites_medias_uploaded} / {len(self.composites_medias)}] -- {int(100 * (nb_composites_medias_uploaded / len(self.composites_medias)))}%', end='\r')

                media_data = media.get('data', {})
                presentation_id = json.loads(media_data.get('external_data', {})).get('id')
                existing_media = self.get_ms_media_by_ref(presentation_id)
                if existing_media:
                    logger.warning(f'Composite presentation {presentation_id} already found on MediaServer (oid: {existing_media["oid"]}, skipping')
                    # consider uploaded so that the final condition works
                    nb_composites_medias_uploaded += 1
                else:
                    # store presentation id in order to skip upload if already present on MS
                    media_data['external_ref'] = presentation_id
                    media_folder = self.composites_folder / presentation_id
                    merge_ok = self.compositor.merge(media_folder)
                    if merge_ok:
                        file_path = media_folder / 'composite.mp4'
                        layout_preset_path = media_folder / 'mediaserver_layout.json'
                        if layout_preset_path.is_file():
                            with open(layout_preset_path) as f:
                                media_data['layout_preset'] = f.read()

                        result = self.upload_local_file(file_path.__str__(), media_data)
                        if result.get('success'):
                            nb_composites_medias_uploaded += 1

                            oid = result['oid']
                            self.add_presentation_redirection(presentation_id, oid)

                            media['ref']['media_oid'] = oid
                            media['ref']['slug'] = result.get('slug')
                            if media_data.get('api_key'):
                                del media_data['api_key']

                            if len(media_data.get('chapters')) > 0:
                                self.add_chapters(media['ref']['media_oid'], chapters=media_data['chapters'])
                        else:
                            logger.error(f"Failed to upload media: {media_data['title']}")
                    else:
                        logger.error(f'Failed to merge videos for presentation {presentation_id}')

                up_ok = (nb_composites_medias_uploaded == len(self.composites_medias))

        return up_ok

    def download_composites_videos(self):
        logger.info(f'Downloading composite videos into {self.composites_folder}.')

        if self.compositor is None:
            self.compositor = VideoCompositor(self.config, self.dl_session, self.mediasite_auth)

        all_ok = False
        medias_completed = 0
        videos_downloaded = 0
        for i, v_composite in enumerate(self.composites_medias):
            print(f'Downloading: [{i} / {len(self.composites_medias)}] -- {i / len(self.composites_medias)}%', end='\r')

            data = v_composite.get('data', {})
            presentation_id = json.loads(data.get('external_data', {})).get('id')
            logger.debug(f"Downloading for presentation {presentation_id}")

            media_folder = self.composites_folder / presentation_id
            media_folder.mkdir(parents=True, exist_ok=True)
            urls = data.get('composites_videos_urls', {})
            if not self.compositor.download_all(urls, media_folder):
                logger.error(f'Failed to download composite videos for presentation {presentation_id}.')
                break
            else:
                medias_completed += 1

        all_ok = (medias_completed == len(self.composites_medias))
        if all_ok:
            logger.info(f'Sucessfully downloaded all composite videos ({len(self.composites_medias)})')
        else:
            logger.error(f'Failed to complete all composite medias download: [{medias_completed} / {len(self.composites_medias)}] medias completed | {videos_downloaded} videos downloaded')
        return all_ok

    def upload_local_file(self, file_path, data):
        logger.debug(f'Uploading local file (composite video) : {file_path}')
        result = self.ms_client.add_media(file_path=file_path, **data)
        return result

    @lru_cache
    def get_channel(self, oid=None, title=None):
        channel = None
        if oid:
            params = {'oid': oid}
        elif title:
            params = {'title': title}
        else:
            logger.error('No title or oid provided for getting channel')
            return channel

        channel = self.ms_client.api('channels/get', method='get', params=params, ignore_404=True)
        if channel and channel.get('success'):
            channel = channel.get('info')
        else:
            logger.error(f'Channel {params.values()} does not exist.')

        return channel

    @lru_cache
    def get_root_channel(self):
        oid = str()
        root_channel = dict()
        try:
            with open('config.json') as f:
                config = json.load(f)
            oid = config.get('mediaserver_parent_channel')
        except Exception as e:
            logger.error('No parent channel configured. See in config.json.')
            logger.debug(e)
            sys.exit(1)

        root_channel = self.get_channel(oid)
        if not root_channel:
            logger.error('Root channel does not exist. Please provide an existing channel oid in config.json')
            sys.exit(1)
        return root_channel

    @lru_cache
    def get_user_channel_oid(self, user_email=None, user_id=None):
        logger.debug(f'Getting user channel for user id {user_id}')
        params = {'create': 'yes'}
        if user_email:
            params['email'] = user_email
        elif user_id:
            params['id'] = user_id
        result = self.ms_client.api('channels/personal/', method='get', params=params)
        #{"allowed": true, "oid": "c125cf1ed2152ufai5gu", "dbid": 1283, "title": "Antoine Peltier", "slug": "antoine-peltier", "success": true}
        # {"error": "L'utilisateur \"6516516651\" n'existe pas.", "success": false}
        if result and result.get('success'):
            channel_oid = result.get('oid')
            return channel_oid
        else:
            logger.error(f"Failed to get user channel for {user_email} / Error: {result.get('error')}")

    def create_user(self, user):
        logger.debug(f"Creating user {user.get('username')}")

        user_id = str()

        try:
            result = self.ms_client.api('users/add', method='post', data=user)
        except MSReqErr as e:
            same_email_error = 'A user with the same email already exists.'
            same_username_error = 'A user with the same username already exists.'
            if same_email_error or same_username_error in e.__str__():
                logger.debug(f"User {user.get('username')} already exists.")
                del user['api_key']
                return user_id
            else:
                result = {'success': False, 'error': e}

        if result.get('success'):
            logger.debug(f"Created user {user.get('username')} with id {result.get('id')}")

            user_id = result.get('id')
            del user['api_key']

            if not user_id:
                logger.warning(f"MediaServer dit not return an id when creating user {user.get('username')}")

            result = self.ms_client.api('perms/edit/', method='post', data={'type': 'user', 'id': user_id, 'can_have_personal_channel': 'True'})
            if not result.get('success'):
                logger.error(f"Failed te granted permission to have personnal channel for user {user.get('username')}")
        else:
            logger.error(f"Failed te create user {user.get('username')} / Error: {result.get('error')}")

        return user_id

    def to_mediaserver_users(self, mediasite_users):
        ms_users = list()

        for user in mediasite_users:
            ms_users.append({
                'email': user.get('mail', ''),
                'username': user.get('username', ''),
                'speaker_id': user.get('display_name', '')
            })

        return ms_users

    @lru_cache
    def channel_has_catalog(self, channel_path):
        for f in self.mediaserver_data:
            if f.get('ref').get('channel_path') == channel_path:
                has_catalog = not f['data']['channel_unlisted']
                return has_catalog
        return False

    @lru_cache
    def create_channels(self, channel_path):
        '''
        Creates all intermediary channels and
        returns the oid of the parent channel
        '''
        logger.debug(f'Creating channel path: {channel_path}')

        # if at least one intermediary folder has a catalog, then the entire tree should be listed:
        # * any upper channels needs to be listed so that users can discover it in MediaServer
        # * any leaf chennels needs to be listed too because mediasite publishes subfolders recursively
        is_unlisted = True
        tree = channel_path.lstrip('/').split('/')
        tree_list = list()  # turn path 'a/b/c/d' into list ['/a/b/c/d', '/a/b/c', '/a/b', '/a']
        for i in range(len(tree) + 1):
            if tree:
                path = '/' + '/'.join(tree)
                if self.channel_has_catalog(path):
                    logger.debug(f'Parent folder {path} has a catalog, making complete path {channel_path} listed')
                    is_unlisted = False
                tree_list.append(path)
                tree.pop(-1)

        # reverses list into ['/a', '/a/b', '/a/b/c', '/a/b/c/d']
        tree_list.reverse()

        oid = self.root_channel.get('oid')
        for leaf in tree_list:
            folder_id = external_data = None
            urls = list()
            folder = self.get_folder_by_path(leaf)
            if folder:
                folder_id = folder['id']
                external_data = json.dumps({
                    'id': folder['id'],
                    'name': folder['name'],
                    'catalogs': folder['catalogs']},
                    indent=2)
                for c in folder['catalogs']:
                    urls.append(c['url'])

            existing_channel = self.get_ms_channel_by_ref(folder_id)
            if existing_channel:
                new_oid = existing_channel['oid']
                logger.warning(f'Channel with external_ref {folder_id} already exists on MediaServer (oid: {new_oid}), skipping creation')
            else:
                channel_title = self.get_channel_title_by_path(leaf)
                new_oid = self._create_channel(
                    parent_channel=oid,
                    channel_title=channel_title,
                    is_unlisted=is_unlisted,
                    original_path=leaf,
                    external_ref=folder_id,
                    external_data=external_data,
                ).get('oid')
                for url in urls:
                    self.redirections[url] = f'/permalink/{oid}/iframe/?header=no'
            oid = new_oid

        # last item in list is the final channel, return it's oid
        # because he will be the parent of the video
        return oid

    def _update_channel(self, channel_oid, unlisted_bool=True, external_ref=None, external_data=None):
        data = {'oid': channel_oid}
        self._set_channel_unlisted(channel_oid, unlisted_bool)
        if external_ref:
            data['external_ref'] = external_ref
        if external_data:
            data['external_data'] = external_data

        result = self.ms_client.api('channels/edit/', method='post', data=data)
        if result and not result.get('success'):
            logger.error(f"Failed to edit channel {channel_oid} with data {data} / Error: {result.get('error')}")
        elif not result:
            logger.error(f'Unknown error when trying to edit channel {channel_oid} with data {data}: {result}')

    def _set_channel_unlisted(self, channel_oid, unlisted_bool):
        data = {'oid': channel_oid}
        # perms/edit/default/ doc:
        # "If any value is given, the unlisted setting will be set as enabled on the channel or media, otherwise it will be disabled."
        # In other terms, calling perms/edit/default/ without unlisted makes it listed
        if unlisted_bool:
            data['unlisted'] = 'yes'
        result = self.ms_client.api('perms/edit/default/', method='post', data=data)
        if result and not result.get('success'):
            logger.error(f"Failed to edit channel perms {channel_oid} with data {data} / Error: {result.get('error')}")
        elif not result:
            logger.error(f'Unknown error when trying to edit channel perms {channel_oid} with data {data}: {result}')

    def _create_channel(self, parent_channel, channel_title, is_unlisted, original_path, external_ref=None, external_data=None):
        logger.debug(f'Creating channel {channel_title} with parent {parent_channel} / is_unlisted : {is_unlisted}')
        channel = dict()

        existing_channel = self.created_channels.get(original_path) or self.channel_already_exists(original_path)
        if existing_channel:
            logger.debug(f'Channel {original_path} already created.')
            if existing_channel.get('is_unlisted') is False:
                # listed takes precedence over unlisted
                # if it is already listed, it cannot be unlisted
                return existing_channel
            elif existing_channel.get('is_unlisted') == is_unlisted:
                # nothing to do
                return existing_channel
            else:
                channel_oid = existing_channel['oid']
                logger.debug(f'Setting unlisted on channel {channel_oid} to {is_unlisted}')
                self._set_channel_unlisted(channel_oid, True)
        else:
            logger.debug(f'Creating channel {original_path}')
            data = {'title': channel_title, 'parent': parent_channel}
            result = self.ms_client.api('channels/add', method='post', data=data)

            if result and not result.get('success'):
                logger.error(f'Failed to create channel: {channel} / Error: {result.get("error")}')
            elif not result:
                logger.error(f'Unknown error when creating channel with {data}')
            else:
                channel = result

                # channels/add does not support unlisted or external_ref or external_data args, we must do another request
                self._update_channel(
                    channel['oid'],
                    unlisted_bool=is_unlisted,
                    external_ref=external_ref,
                    external_data=external_data,
                )

                self.created_channels[original_path] = {
                    'title': channel_title,
                    'oid': channel.get('oid'),
                    'is_unlisted': is_unlisted,
                }

        return channel

    def migrate_slides(self, media):
        media_oid = media['ref'].get('media_oid')
        media_slides = media['data'].get('slides')
        nb_slides_downloaded, nb_slides_uploaded, nb_slides = 0, 0, 0

        if media_slides:
            if media_slides.get('stream_type') == 'Slide' and media_slides.get('details'):
                slides_dir = self.slides_folder / media_oid
                slides_dir.mkdir(parents=True, exist_ok=True)
                nb_slides_downloaded, nb_slides_uploaded, nb_slides = self._migrate_slides(media)
            else:
                logger.debug(f'Media {media_oid} has slides binded to video (no timecode). Detect slides will be lauched in Mediaserver.')

        logger.debug(f"{nb_slides_downloaded} slides downloaded and {nb_slides_uploaded} uploaded (amongs {nb_slides} slides) for media {media['ref']['media_oid']}")

        return nb_slides_uploaded, nb_slides

    def _migrate_slides(self, media):
        media_oid = media['ref']['media_oid']
        media_slides = media['data']['slides']
        media_slides_details = media['data']['slides']['details']
        nb_slides = len(media_slides.get('urls', []))
        nb_slides_downloaded = 0
        nb_slides_uploaded = 0

        if self.dl_session is None:
            self.dl_session = requests.Session()

        logger.debug(f'Migrating slides for medias: {media_oid}')
        for i, url in enumerate(media_slides['urls']):
            if self.e2e_test:
                path = url
            else:
                slide_dl_ok, path = self._download_slide(media_oid, url)
                if slide_dl_ok:
                    nb_slides_downloaded += 1
                else:
                    logger.error(f'Failed to download slide {i + 1} for media {media_oid}')

            if self.slide_annot_type is None:
                self.slide_annot_type = self._get_annotation_type_id(media_oid, annot_type='slide')
            details = {
                'oid': media_oid,
                'time': media_slides_details[i].get('TimeMilliseconds'),
                'title': media_slides_details[i].get('Title'),
                'content': media_slides_details[i].get('Content'),
                'type': self.slide_annot_type
            }
            with open(path, 'rb') as file:
                result = self.ms_client.api('annotations/post/', method='post', data=details, files={'attachment': file})
            slide_up_ok = result.get('annotation')
            if slide_up_ok is not None:
                nb_slides_uploaded += 1

        return nb_slides_downloaded, nb_slides_uploaded, nb_slides

    def _download_slide(self, media_oid, url):
        ok = False
        filename = url.split('/').pop()
        path = self.slides_folder / media_oid / filename

        if os.path.exists(path):
            # do not re-download
            ok = True
        else:
            r = self.dl_session.get(url, auth=self.mediasite_auth)
            if r.ok:
                with open(path, 'wb') as f:
                    f.write(r.content)
                ok = r.ok
            else:
                logger.error(f'Failed to download {url}')

        return ok, path

    def _get_annotation_type_id(self, media_oid, annot_type):
        annotation_type = int()

        result = self.ms_client.api('annotations/types/list/', method='get', params={'oid': media_oid})
        if result.get('success'):
            for a in result.get('types'):
                if a.get('slug') == annot_type:
                    annotation_type = a.get('id')

        return annotation_type

    def _send_audio_thumb(self, media_oid):
        file = open('mediasite_migration_scripts/files/utils/audio.jpg', 'rb')
        result = self.ms_client.api('medias/edit', method='post', data={'oid': media_oid}, files={'thumb': file})
        file.close()
        return result.get('success')

    def add_presentation_redirection(self, presentation_id, oid):
        mediasite_presentation_url = self.get_presentation_url(presentation_id)
        if mediasite_presentation_url:
            self.redirections[mediasite_presentation_url] = f'/permalink/{oid}/iframe/'

    def get_presentation_url(self, presentation_id):
        presentation = self.get_presentation_by_id(presentation_id)
        if presentation:
            return presentation.get('url')

    @lru_cache
    def get_presentation_by_id(self, presentation_id):
        for f in self.mediasite_data:
            for presentation in f['presentations']:
                if presentation['id'] == presentation_id:
                    return presentation

    def to_mediaserver_keys(self):
        logger.debug('Matching Mediasite data to MediaServer keys mapping.')
        logger.debug(f'Whitelist: {self.config.get("whitelist")}')

        mediaserver_data = list()
        if hasattr(self, 'mediaserver_data'):
            mediaserver_data = self.mediaserver_data
        else:
            logger.debug('No Mediaserver mapping. Generating mapping.')
            for folder in self.mediasite_data:
                if utils.is_folder_to_add(folder.get('path'), config=self.config):
                    has_catalog = (len(folder.get('catalogs', [])) > 0)

                    is_unlisted_channel = not has_catalog
                    for p in self.public_paths:
                        if folder['path'].startswith(p):
                            is_unlisted_channel = False
                            break

                    for presentation in folder['presentations']:
                        presenters = str()
                        for p in presentation.get('other_presenters'):
                            presenters += p.get('display_name', '')

                        description_text = presentation.get('description', '')
                        description_text = description_text if description_text else ''
                        presenters = f'[Presenters: {presenters}] \n<br/>' if presenters else ''
                        description = f'{presenters}{description_text}'

                        v_composites_urls = list()
                        v_files = None
                        videos = presentation.get('videos', [])
                        v_type, slides_source = self._find_video_type(presentation)
                        v_url = 'local'
                        if v_type in ('composite_video', 'composite_slides'):
                            v_composites_urls = self._get_composite_video_resources(presentation)
                        else:
                            if slides_source:
                                for v in videos:
                                    if v.get('stream_type') == slides_source:
                                        v_files = v.get('files')
                                        break
                            else:
                                v_files = videos[0].get('files', [])

                            v_url = self._find_file_to_upload(v_files)

                        if v_url:
                            has_catalog = len(folder.get('catalogs', [])) > 0
                            channel_name = folder.get('name')

                            ext_data = presentation if self.config.get('external_data') else {
                                key: presentation.get(key) for key in ['id', 'creator', 'total_views', 'last_viewed']
                            }

                            if v_type == 'video_slides':
                                layout = 'webinar'
                            elif v_type in ['composite_video', 'composite_slides']:
                                layout = 'composition'
                            else:
                                layout = 'video'

                            data = {
                                'title': presentation.get('title'),
                                'channel_title': channel_name,
                                'channel_unlisted': is_unlisted_channel,
                                'unlisted': 'yes' if is_unlisted_channel else 'no',
                                'creation': presentation.get('creation_date'),
                                'speaker_id': presentation.get('owner_username'),
                                'speaker_name': presentation.get('owner_display_name'),
                                'speaker_email': presentation.get('owner_mail').lower(),
                                'validated': 'yes' if presentation.get('published_status') else 'no',
                                'description': description,
                                'keywords': ','.join(presentation.get('tags')),
                                'slug': 'mediasite-' + presentation.get('id'),
                                'external_data': json.dumps(ext_data, indent=2, sort_keys=True),
                                'transcode': 'yes' if v_type in ['audio_only', 'composite_slides', 'composite_video'] else 'no',
                                'origin': 'mediatransfer',
                                'detect_slides': 'yes' if v_type in ['computer_slides', 'composite_slides'] else 'no',
                                'layout': layout,
                                'slides': presentation.get('slides'),
                                'chapters': presentation.get('timed_events'),
                                'video_type': v_type,
                                'file_url': v_url,
                                'composites_videos_urls': v_composites_urls
                            }

                            folder_path = folder.get('path')
                            if has_catalog:
                                channel_path_splitted = folder_path.split('/')
                                channel_path_splitted[-1] = channel_name
                                channel_path = '/'.join(channel_path_splitted)
                            else:
                                channel_path = folder_path

                            if v_type == 'audio_only':
                                data['thumb'] = 'mediasite_migration_scripts/files/utils/audio.jpg'

                            mediaserver_data.append({'data': data, 'ref': {'channel_path': channel_path, 'folder_path': folder_path}})
                        else:
                            logger.warning(f"No valid video for presentation {presentation.get('id')}")
                            continue

        return mediaserver_data

    def _find_video_type(self, presentation):
        video_type = str()
        slides_source = None
        if presentation.get('slides'):
            if presentation.get('slides').get('details'):
                if len(presentation.get('videos')) > 1:
                    video_type = 'composite_video'
                else:
                    video_type = 'audio_slides'
                    for f in presentation.get('videos', [])[0].get('files'):
                        if f.get('encoding_infos').get('video_codec'):
                            video_type = 'video_slides'
                            break
            elif presentation['slides'].get('stream_type', '').startswith('Video'):
                slides_source = presentation['slides'].get('stream_type')
                if len(presentation['slides'].get('urls')) > 0:
                    if len(presentation.get('videos')) > 1:
                        video_type = 'composite_slides'
                    else:
                        video_type = 'computer_slides'
                else:
                    video_type = 'audio_only'
                    for f in presentation.get('videos', [])[0].get('files', []):
                        if f.get('encoding_infos', {}).get('video_codec'):
                            video_type = 'computer_only'
                            break
        elif len(presentation.get('videos')) > 1:
            video_type = 'composite_video'
        else:
            video_type = 'audio_only'
            for f in presentation.get('videos', [])[0].get('files', []):
                if f.get('encoding_infos', {}).get('video_codec'):
                    video_type = 'video_only'

        return video_type, slides_source

    def _get_composite_video_resources(self, presentation):
        videos = dict()
        slides_stream_type = presentation.get('slides', {}).get('stream_type')
        for video in presentation['videos']:
            name = video['stream_type']
            if name == slides_stream_type:
                name = 'Slides'
            for f in video['files']:
                if f['size_bytes'] > 0 and f['format'] == 'video/mp4':
                    videos[name] = f['url']
                    break
        return videos

    def _find_file_to_upload(self, video_files):
        video_url = str()
        for file in video_files:
            if file.get('format') == 'video/mp4':
                video_url = file['url']
                break
            elif self.formats_allowed.get(file.get('format')):
                video_url = file['url']
                break

        return video_url

    def add_chapters(self, media_oid, chapters):
        logger.debug(f'Adding chapters for media {media_oid}')

        ok = True
        if self.chapters_annot_type is None:
            self.chapters_annot_type = self._get_annotation_type_id(media_oid, annot_type='chapter')

        for c in chapters:
            data = {
                'oid': media_oid,
                'title': c.get('chapter_title'),
                'time': c.get('chapter_position_ms'),
                'type': self.chapters_annot_type
            }
            result = self.ms_client.api('annotations/post', method='post', data=data)
            ok = result.get('success', False)

        return ok

    def get_folder_by_path(self, path):
        for f in self.mediasite_data:
            if f['path'] == path:
                return f

    @lru_cache
    def get_channel_title_by_path(self, path):
        folder = self.get_folder_by_path(path)
        if folder:
            title = self.get_final_channel_title(folder)
        else:
            logger.warning(f'Did not find folder for {path}, falling back to last item')
            title = path.split('/')[-1]
        return title

    def get_final_channel_title(self, folder):
        '''
        The MediaServer channel title should take the most recent
        catalog name (if any), otherwise use the folder name.
        '''
        name = folder['name']
        most_recent_time = None
        most_recent_catalog = None
        for c in folder['catalogs']:
            catalog_date = utils.parse_mediasite_date(c['creation_date'])
            if most_recent_time is None or catalog_date > most_recent_time:
                most_recent_time = catalog_date
                most_recent_catalog = c
        if most_recent_catalog is not None:
            name = most_recent_catalog['name']
            logger.debug(f'Overriding channel name with the most recent catalog name {name}')
        return name
