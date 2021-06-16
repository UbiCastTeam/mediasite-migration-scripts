import logging
import json
import time
import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import sys
from pathlib import Path
from functools import lru_cache

from mediasite_migration_scripts.ms_client.client import MediaServerClient
from mediasite_migration_scripts.utils import common as utils
import mediasite_migration_scripts.utils.http as http
from mediasite_migration_scripts.ms_client.client import MediaServerRequestError as MSReqErr
from mediasite_migration_scripts.video_compositor import VideoCompositor


logger = logging.getLogger(__name__)


class MediaTransfer():

    def __init__(self, config=dict(), mediasite_data=dict(), mediasite_users=dict(), download_folder=None, slides_download=None, unit_test=False, e2e_test=False, root_channel_oid=None):
        self.config = config

        self.compositor = None
        self.composites_medias = list()
        self.medias_folders = list()
        self.created_channels = dict()
        self.slide_annot_type = None
        self.chapters_annot_type = None
        self.processed_count = self.uploaded_count = self.composite_uploaded_count = self.skipped_count = self.uploaded_slides_count = self.skipped_slides_count = self.skipped_chapters_count = 0
        self.media_with_missing_slides = list()
        self.failed = list()

        if download_folder:
            self.download_folder = dl = Path(download_folder)
        elif config.get('download_folder'):
            self.download_folder = dl = Path(config.get('download_folder'))
        else:
            logger.error('Please provide a download folder path. Not found in config.json or in argument.')
            sys.exit(1)
        self.slides_folder = dl / 'slides'
        self.composites_folder = dl / 'composite'

        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.dl_session = requests.Session()
        self.dl_session.mount('https://', adapter)
        self.dl_session.mount('http://', adapter)

        self.mediasite_data = mediasite_data
        self.formats_allowed = self.config.get('videos_formats_allowed', {})
        self.mediasite_auth = (self.config.get('mediasite_api_user'), self.config.get('mediasite_api_password'))
        self.mediasite_userfolder = config.get('mediasite_userfolder', '/Mediasite Users/')
        self.unknown_users_channel_title = config.get('mediaserver_unknown_users_channel_title', 'Mediasite Unknown Users')
        self.redirections_file = Path(config.get('redirections_file', 'redirections.json'))
        if self.redirections_file.is_file():
            print(f'Loading redirections file {self.redirections_file}')
            with open(self.redirections_file, 'r') as f:
                self.redirections = json.load(f)
        else:
            self.redirections = dict()

        self.e2e_test = e2e_test
        self.unit_test = unit_test

        if self.unit_test:
            self.config['videos_format_allowed'] = {'video/mp4': True, "video/x-ms-wmv": False}
        else:
            self.ms_config = utils.to_mediaserver_conf(self.config)
            self.ms_client = MediaServerClient(local_conf=self.ms_config, setup_logging=False)

            if root_channel_oid:
                self.root_channel = self.get_channel(root_channel_oid)
            else:
                self.root_channel = self.get_root_channel()

        self.public_paths = [folder.get('path', '') for folder in mediasite_data if len(folder.get('catalogs')) > 0]

        self.mediaserver_data = self.to_mediaserver_keys()

    def write_redirections_file(self):
        if self.redirections:
            logger.info(f'Writing redirections file {self.redirections_file}')
            with open(self.redirections_file, 'w') as f:
                json.dump(self.redirections, f, indent=2)
        else:
            logger.info('No redirections to write')

    def dump_incomplete_media(self):
        incomplete_file = 'incomplete_presentations.csv'
        if self.media_with_missing_slides:
            logger.info(f'Writing {len(self.media_with_missing_slides)} oids in {incomplete_file}')
            with open(incomplete_file, 'a') as f:
                for oid in self.media_with_missing_slides:
                    f.write(oid + ',missing_slides\n')

    def upload_medias(self, max_videos=None):
        before = time.time()
        if max_videos:
            try:
                max_videos = int(max_videos)
                total_count = max_videos
            except Exception as e:
                logger.error(f'{max_videos} is not a valid number for videos maximum.')
                logger.debug(e)
        else:
            total_count = len(self.mediaserver_data)

        logger.info(f'{total_count} medias found for uploading.')

        for index, media in enumerate(self.mediaserver_data):
            if sys.stdout.isatty():
                print(utils.get_progress_string(index, total_count) + ' Uploading non-composites presentations or preparing folders', end='\r')
            self.processed_count += 1

            if max_videos and index >= max_videos:
                break

            if not media.get('ref', {}).get('media_oid'):
                try:
                    data = media.get('data', {})  # mediaserver data
                    presentation_id = json.loads(data.get('external_data', '{}')).get('id')

                    channel_path = media['ref'].get('channel_path')
                    if channel_path.startswith(self.mediasite_userfolder):
                        if self.config.get('skip_userfolders'):
                            continue
                        folder_id = self.get_folder_by_path(channel_path).get('id')
                        existing_channel = self.get_ms_channel_by_ref(folder_id)
                        if existing_channel:
                            target_channel = 'mscid-' + existing_channel['oid']
                        else:
                            target_channel = self.get_personal_channel_target(channel_path, folder_id)
                            if target_channel is None:
                                logger.warning(f'Could not find personal target channel for path {channel_path}, skipping media')
                                continue
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
                    else:
                        if self.config.get('skip_others'):
                            continue
                        existing_media = self.get_ms_media_by_ref(presentation_id)
                        if existing_media:
                            media_oid = media['ref']['media_oid'] = existing_media['oid']
                            logger.warning(f'Presentation {presentation_id} already present on MediaServer (oid: {media_oid}), not reuploading')
                        else:
                            # store original presentation id to avoid duplicates
                            data['external_ref'] = presentation_id

                            # mediaserver currently crashes when providing more than 254 characters in keywords
                            # keeping in mind that it replaces "," by ", " (2 chars) we need to truncate it by
                            # 254 - count(',') * 2
                            if data['keywords']:
                                truncate_to = 254 - data['keywords'].count(',') * 2
                                data['keywords'] = data['keywords'][:truncate_to]

                            # lower transcoding priority
                            data['priority'] = 'low'
                            result = self.ms_client.api('medias/add', method='post', data=data)
                            if result.get('success'):
                                self.uploaded_count += 1
                                media_oid = result['oid']
                                self.add_presentation_redirection(presentation_id, media_oid)
                                media['ref']['media_oid'] = media_oid
                                media['ref']['slug'] = result.get('slug')
                                if data.get('api_key'):
                                    del data['api_key']

                                if data.get('video_type') == 'audio_only':
                                    thumb_ok = self._send_audio_thumb(media['ref']['media_oid'])
                                    if not thumb_ok:
                                        logger.warning('Failed to upload audio thumbail for audio presentation')

                                if len(data.get('chapters')) > 0:
                                    self.add_chapters(media['ref']['media_oid'], chapters=data['chapters'])
                            else:
                                logger.error(f"Failed to upload media: {presentation_id}")
                                self.failed.append(presentation_id)

                        if not self.slides_already_uploaded(media_oid):
                            self.migrate_slides(media)

                except requests.exceptions.ReadTimeout:
                    logger.warning('Request timeout. Another attempt will be lauched at the end.')
                    continue

        self.migrate_composites_videos()

        print('')

        self.ms_client.session.close()
        if self.dl_session is not None:
            self.dl_session.close()

        took = time.time() - before
        logger.info(f'Finished processing {self.processed_count} media in {int(took)}s / {utils.get_timecode_from_sec(took)}')
        if self.uploaded_count:
            took_per_media = took / self.uploaded_count
            logger.info(f'Uploaded {self.uploaded_count} media ({utils.get_timecode_from_sec(took_per_media)} per media)')

        # uploaded_composites is included in uploaded
        stats = {
            'processed': self.processed_count,
            'uploaded': self.uploaded_count,
            'uploaded_composites': self.composite_uploaded_count,
            'uploaded_slides': self.uploaded_slides_count,
            'skipped': self.skipped_count,
            'skipped_slides': self.skipped_slides_count,
            'skipped_chapters_count': self.skipped_chapters_count,
            'failed': len(self.failed),
        }

        if self.failed:
            logger.error(f'{len(self.failed)} media failed to migrate: {self.failed}')

        return stats

    @lru_cache
    def get_personal_channel_target(self, channel_path, folder_id):
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
            if channel_oid:
                if len(subfolders) > 1:
                    # Mediasite Users/USERNAME
                    spath = self.mediasite_userfolder + subfolders[0] + '/'
                    for s in subfolders[1:]:
                        spath += s + '/'
                        channel_oid = self._create_channel(channel_oid, s, True, spath, external_ref=folder_id)['oid']
                target = f'mscid-{channel_oid}'
            else:
                logger.warning(f'User {username} is probably not allowed to have a personal channel')
                return
        else:
            # user does not exist
            subfolders_path = "/".join(subfolders)
            target = f'mscpath-{self.unknown_users_channel_title}/{subfolders_path}'
        return target

    def search_mediasite_id_in_redirections(self, mediasite_id):
        # it is much faster to lookup the local redirections file than to perform an API request
        for from_url, to_url in self.redirections.items():
            if mediasite_id in from_url:
                oid = to_url.split('/')[4]
                return oid

    def get_ms_media_by_ref(self, external_ref):
        oid = self.search_mediasite_id_in_redirections(external_ref)
        if oid:
            return {'oid': oid}
        return self.search_by_external_ref(external_ref, object_type='media')

    def get_ms_channel_by_ref(self, external_ref):
        oid = self.search_mediasite_id_in_redirections(external_ref)
        if oid:
            return {'oid': oid}
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
        total_composite = len(self.composites_medias)
        logger.info(f'Merging and migrating {total_composite} composite videos')

        self.download_composites_videos()

        for index, media in enumerate(self.composites_medias):
            self.processed_count += 1
            if sys.stdout.isatty():
                print(utils.get_progress_string(index, total_composite) + ' Uploading composite', end='\r')

            media_data = media.get('data', {})
            presentation_id = json.loads(media_data.get('external_data', {})).get('id')
            existing_media = self.get_ms_media_by_ref(presentation_id)
            if existing_media:
                logger.warning(f'Composite presentation {presentation_id} already found on MediaServer (oid: {existing_media["oid"]}, skipping')
                self.skipped_count += 1
                # consider uploaded so that the final condition works
            else:
                # store presentation id in order to skip upload if already present on MS
                media_data['external_ref'] = presentation_id
                media_folder = self.composites_folder / presentation_id
                layout_preset_path = media_folder / 'mediaserver_layout.json'
                if not media_folder.is_dir():
                    logger.warning(f'Missing downloads folder for {presentation_id}, skipping')
                    continue
                if not layout_preset_path.is_file():
                    self.compositor.merge(media_folder)

                if layout_preset_path.is_file():
                    file_path = media_folder / 'composite.mp4'
                    if layout_preset_path.is_file():
                        with open(layout_preset_path) as f:
                            media_data['layout_preset'] = f.read()

                    # reduce transcoding priority
                    media_data['priority'] = 'low'

                    result = self.upload_local_file(file_path.__str__(), media_data)
                    if result.get('success'):
                        self.uploaded_count += 1
                        self.composite_uploaded_count += 1

                        oid = result['oid']
                        self.add_presentation_redirection(presentation_id, oid)

                        media['ref']['media_oid'] = oid
                        media['ref']['slug'] = result.get('slug')
                        if media_data.get('api_key'):
                            del media_data['api_key']

                        if len(media_data.get('chapters')) > 0:
                            self.add_chapters(media['ref']['media_oid'], chapters=media_data['chapters'])
                    else:
                        logger.error(f"Failed to upload media: {presentation_id}")
                        self.failed.append(presentation_id)
                else:
                    logger.error(f'Failed to merge videos for presentation {presentation_id}')

    def download_composites_videos(self):
        logger.info(f'Downloading composite videos into {self.composites_folder}.')
        if self.compositor is None:
            self.compositor = VideoCompositor(self.config, self.dl_session, self.mediasite_auth)

        for i, v_composite in enumerate(self.composites_medias):
            print(utils.get_progress_string(i, len(self.composites_medias)) + ' Downloading composite', end='\r')
            data = v_composite.get('data', {})
            presentation_id = json.loads(data.get('external_data', {})).get('id')
            logger.debug(f"Downloading for presentation {presentation_id}")
            media_folder = self.composites_folder / presentation_id
            media_folder.mkdir(parents=True, exist_ok=True)
            urls = data.get('composites_videos_urls', {})
            if (media_folder / 'mediaserver_layout.json').is_file():
                pass
            elif not self.compositor.download_all(urls, media_folder):
                logger.warning(f'Failed to download composite videos for presentation {presentation_id}.')
            else:
                pass

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

        channel = self.ms_client.api('channels/get', method='get', params=params)
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
            key = 'email'
            val = user_email
        elif user_id:
            key = 'id'
            val = user_id
        params[key] = val
        result = self.ms_client.api('channels/personal/', method='get', params=params)
        if result:
            if isinstance(result, dict):
                if result.get('success'):
                    channel_oid = result['oid']
                    return channel_oid
                else:
                    error = result.get('error', '')
                    if user_id and '403' in error:
                        #{'error': 'Access denied (403)', 'message': '', 'success': False}
                        logger.info(f'Granting permission to own a personal channel to user with id {user_id}')
                        data = {
                            'type': 'user',
                            'id': user_id,
                            'can_have_personal_channel': 'True',
                            'can_create_media': 'True',
                        }
                        result = self.ms_client.api('perms/edit/', method='post', data=data)
                        return self.get_user_channel_oid(user_id=user_id)
                    else:
                        logger.error(f'Failed to get user channel for {key}={val} / Error: {error}')
            else:
                logger.error(f'Failed to get user channel: unknown error {result}')

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
                logger.debug(f'Channel with external_ref {folder_id} already exists on MediaServer (oid: {new_oid}), skipping creation')
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
                    self.redirections[url] = self.get_full_ms_url(f'/permalink/{new_oid}/iframe/?header=no')
            oid = new_oid

        # last item in list is the final channel, return it's oid
        # because he will be the parent of the video
        return oid

    def get_full_ms_url(self, suffix):
        ms_prefix = self.config["mediaserver_url"].rstrip('/')
        return f'{ms_prefix}/{suffix.lstrip("/")}'

    def _update_channel(self, channel_oid, unlisted_bool=True, external_ref=None, external_data=None):
        data = {'oid': channel_oid}
        self._set_channel_unlisted(channel_oid, unlisted_bool)
        if external_ref:
            data['external_ref'] = external_ref
        if external_data:
            data['external_data'] = external_data

        result = self.ms_client.api('channels/edit/', method='post', data=data)
        if result and not result.get('success'):
            logdata = dict(data)
            logdata.pop('api_key', None)  # hide api key from logs
            logger.error(f"Failed to edit channel {channel_oid} with data {logdata} / Error: {result.get('error')}")
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

        existing_channel = self.created_channels.get(original_path)
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
        presentation_id = json.loads(media['data']['external_data'])['id']
        media_slides = media['data'].get('slides')
        nb_slides_uploaded, nb_slides = 0, 0

        if media_slides:
            logger.debug(f"Migrating slides for medias: {media['ref']['media_oid']}")

            if media_slides.get('stream_type') == 'Slide' and media_slides.get('details'):
                slides_dir = self.slides_folder / presentation_id
                nb_slides = len(media_slides)
                nb_slides_uploaded = self._upload_slides(media, slides_dir)
                self.uploaded_slides_count += nb_slides_uploaded
            else:
                logger.debug(f"Media {media['ref']['media_oid']} has slides binded to video (no timecode). Detect slides will be lauched in Mediaserver.")

        logger.debug(f"{nb_slides_uploaded} uploaded (amongs {nb_slides} slides) for media {media['ref']['media_oid']}")

        return nb_slides_uploaded, nb_slides

    def _upload_slides(self, media, slides_dir):
        media_oid = media['ref']['media_oid']
        media_slides_details = media['data']['slides']['details']
        nb_slides_uploaded = 0

        if self.dl_session is None:
            self.dl_session = requests.Session()
        if self.slide_annot_type is None:
            self.slide_annot_type = self._get_annotation_type_id(media_oid, annotation_type='slide')

        logger.debug(f'Uploading slides for medias: {media_oid}')
        for i, slide_path in enumerate(slides_dir.iterdir()):
            details = {
                'oid': media_oid,
                'time': media_slides_details[i].get('TimeMilliseconds'),
                'title': media_slides_details[i].get('Title'),
                'content': media_slides_details[i].get('Content'),
                'type': self.slide_annot_type
            }
            success = self._add_annotation_safe(details, slide_path)
            if success:
                with open(slide_path, 'rb') as file:
                    result = self.ms_client.api('annotations/post/', method='post', data=details, files={'attachment': file})
                    slide_up_ok = result.get('annotation')
                if slide_up_ok is not None:
                    nb_slides_uploaded += 1
                else:
                    self.skipped_slides_count += 1

        return nb_slides_uploaded

    def _get_annotation_type_id(self, media_oid, annotation_type):
        annotation_type = int()

        result = self.ms_client.api('annotations/types/list/', method='get', params={'oid': media_oid})
        if result.get('success'):
            for a in result.get('types'):
                if a.get('slug') == annotation_type:
                    annotation_type = a.get('id')

        return annotation_type

    def _add_annotation_safe(self, data, path=None):
        media_oid = data['oid']
        arguments = {
            'method': 'post',
            'data': data,
            'ignored_error_strings': ["The timecode can't be superior to the video duration"]  # mediasite may have slides with timecodes after the duration of the video
        }
        if path:
            # slide upload
            with open(path, 'rb') as f:
                arguments['files'] = {'attachment': f}
                result = self.ms_client.api('annotations/post/', **arguments)
        else:
            result = self.ms_client.api('annotations/post/', **arguments)
        if result and result.get('annotation'):
            return True
        else:
            logger.error(f'Failed to add annotation on media {media_oid} with data {data}, ignoring annotation')
            self.skipped_slides_count += 1
            if media_oid not in self.media_with_missing_slides:
                self.media_with_missing_slides.append(media_oid)
            return False

    def slides_already_uploaded(self, media_oid):
        already_up = True

        result = self.ms_client.api('annotations/slides/list', method='get', params={'oid': media_oid})
        # if media not found (success = false), same behavior if already_up (do not upload)
        already_up = not (result.get('success') and len(result.get('slides')) == 0)
        if already_up:
            logger.warning(f'Slides already uploaded for media {media_oid}')

        return already_up

    def _send_audio_thumb(self, media_oid):
        file = open('mediasite_migration_scripts/files/utils/audio.jpg', 'rb')
        result = self.ms_client.api('medias/edit', method='post', data={'oid': media_oid}, files={'thumb': file})
        file.close()
        return result.get('success')

    def add_presentation_redirection(self, presentation_id, oid):
        mediasite_presentation_url = self.get_presentation_url(presentation_id)
        if mediasite_presentation_url:
            self.redirections[mediasite_presentation_url] = self.get_full_ms_url(f'/permalink/{oid}/iframe/')

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
            logger.info('No Mediaserver mapping. Generating mapping.')
            for index, folder in enumerate(self.mediasite_data):
                print(utils.get_progress_string(index, len(self.mediasite_data)) + ' Pre-processing folders and checking resources', end='\r')
                if utils.is_folder_to_add(folder.get('path'), config=self.config):
                    has_catalog = (len(folder.get('catalogs', [])) > 0)

                    is_unlisted_channel = not has_catalog
                    for p in self.public_paths:
                        if folder['path'].startswith(p):
                            is_unlisted_channel = False
                            break

                    for presentation in folder['presentations']:
                        v_composites_urls = list()
                        v_files = v_url = None

                        presentation_id = presentation['id']
                        # there is no use in checking if the video is available if we already processed it
                        if self.search_mediasite_id_in_redirections(presentation_id):
                            continue

                        presenters = list()
                        for p in presentation.get('other_presenters'):
                            presenter_name = p.get('display_name')
                            if presenter_name:
                                presenters.append(presenter_name)

                        description = ''
                        if presenters:
                            description = 'Presenters: ' + ', '.join(presenters)
                        original_description = presentation.get('description')
                        if original_description:
                            description += '\n<br/>' + original_description

                        videos = presentation.get('videos', [])
                        v_type, slides_source = self._find_video_type(presentation)
                        if v_type in ('composite_video', 'composite_slides'):
                            v_composites_urls = self._get_composite_video_resources(presentation)
                            if v_composites_urls:
                                v_url = 'local'
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

                            do_transcode = 'no'
                            if v_type in ['audio_only', 'composite_slides', 'composite_video']:
                                do_transcode = 'yes'
                            elif v_url.endswith('.wmv'):
                                do_transcode = 'yes'

                            data = {
                                'title': presentation.get('title'),
                                'channel_title': channel_name,
                                'channel_unlisted': is_unlisted_channel,
                                'creation': presentation.get('creation_date'),
                                'speaker_id': presentation.get('owner_username'),
                                'speaker_name': presentation.get('owner_display_name'),
                                'speaker_email': presentation.get('owner_mail').lower(),
                                'validated': 'yes' if presentation.get('published_status') else 'no',
                                'description': description,
                                'keywords': ','.join(presentation.get('tags')),
                                'slug': 'mediasite-' + presentation.get('id'),
                                'external_data': json.dumps(ext_data, indent=2, sort_keys=True),
                                'transcode': do_transcode,
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
                            logger.warning(f"No valid video for presentation {presentation.get('id')}, skipping")
                            self.skipped_count += 1
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
        presentation_id = presentation['id']
        slides_stream_type = presentation.get('slides', {}).get('stream_type')
        for video in presentation['videos']:
            name = video['stream_type']
            if name == slides_stream_type:
                name = 'Slides'
            for f in video['files']:
                if f['size_bytes'] > 0 and f['format'] == 'video/mp4':
                    url = f['url']
                    if (self.composites_folder / presentation_id / 'mediaserver_layout.json').is_file() or http.url_exists(url, self.dl_session):
                        videos[name] = f['url']
                        break
        return videos

    def _find_file_to_upload(self, video_files):
        video_url = ''
        for file in video_files:
            url = file['url']
            if file.get('format') == 'video/mp4':
                if file['encoding_infos'].get('video_codec', '') == 'H264' and http.url_exists(url, self.dl_session):
                    video_url = url
                    break
            elif self.formats_allowed.get(file.get('format')):
                if http.url_exists(url, self.dl_session):
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
            success = self._add_annotation_safe(data)
            if not success:
                self.skipped_chapters_count += 1

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
