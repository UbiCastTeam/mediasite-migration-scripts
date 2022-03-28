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
from mediasite_migration_scripts.video_compositor import VideoCompositor

from mediasite_migration_scripts.utils import http, order
import mediasite_migration_scripts.utils.common as utils
import mediasite_migration_scripts.utils.mediasite as mediasite_utils


logger = logging.getLogger(__name__)


class MediaTransfer():

    def __init__(self, config=dict(), mediasite_data=dict()):
        self.config = config
        self.mediasite_folders = mediasite_data.get('Folders')
        self.mediasite_users = mediasite_data.get('UserProfiles')
        self.mediasite_auth = requests.auth.HTTPBasicAuth(self.config.get('mediasite_api_user'), self.config.get('mediasite_api_password'))
        self.mediasite_userfolder = self.config.get('mediasite_userfolder', '/Mediasite Users/')
        self.formats_allowed = self.config.get('videos_formats_allowed', {})

        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.dl_session = requests.Session()
        self.dl_session.mount('https://', adapter)
        self.dl_session.mount('http://', adapter)
        if config.get('download_folder'):
            self.download_folder = dl = Path(config.get('download_folder'))
        else:
            logger.error('Please provide a download folder path. Not found in config.json or in argument.')
            sys.exit(1)

        self.slides_folder = dl / 'slides'
        self.composites_folder = dl / 'composite'

        self.compositor = None
        self.composites_medias = list()
        self.medias_folders = list()
        self.created_channels = dict()
        self.slide_annot_type = None
        self.chapters_annot_type = None
        self.media_with_missing_slides = list()
        self.failed = list()
        self.stats = [
            'processed_count',
            'uploaded_count',
            'composite_uploaded_count',
            'skipped_count',
            'uploaded_slides_count',
            'skipped_slides_count',
            'skipped_chapters_count'
        ]
        for stat in self.stats:
            setattr(self, stat, 0)

        self.unknown_users_channel_title = config.get('mediaserver_unknown_users_channel', 'Mediasite Unknown Users')

        self.redirections_file = Path(config.get('redirections_file', 'redirections.json'))
        if self.redirections_file.is_file():
            print(f'Loading redirections file {self.redirections_file}')
            with open(self.redirections_file, 'r') as f:
                self.redirections = json.load(f)
        else:
            self.redirections = dict()

        self.ms_config = utils.to_mediaserver_conf(self.config)
        self.ms_client = MediaServerClient(local_conf=self.ms_config, setup_logging=False)

        root_channel_oid = config.get('mediaserver_parent_channel')
        if root_channel_oid:
            self.root_channel = self.get_channel(root_channel_oid)
        else:
            self.root_channel = self.get_root_channel()

        self.all_paths = {folder['Id']: self.find_folder_path(folder['Id']) for folder in self.mediasite_folders}
        self.public_paths = [self.find_folder_path(
            folder['Id']) for folder in self.mediasite_folders if len(folder.get('Catalogs', [])) > 0]
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
                utils.print_progress_string(
                    index,
                    total_count,
                    title='Uploading non-composites presentations or preparing folders')
            self.processed_count += 1

            if max_videos and index >= max_videos:
                break

            if not media.get('ref', {}).get('media_oid'):
                try:
                    data = media.get('data', {})  # mediaserver data
                    presentation_id = json.loads(data.get('external_data', {})).get('Id')

                    channel_path = media['ref'].get('channel_path')
                    if channel_path.startswith(self.mediasite_userfolder):
                        if self.config.get('skip_userfolders'):
                            continue
                        folder_id = self.get_folder_by_path(channel_path).get('Id')
                        existing_channel = self.get_ms_channel_by_ref(folder_id)
                        if existing_channel:
                            target_channel = 'mscid-' + existing_channel['oid']
                        else:
                            target_channel = self.get_personal_channel_target(channel_path, folder_id)
                            if target_channel is None:
                                logger.warning(f'Could not find personal target channel for path {channel_path}, skipping media')
                                continue
                    else:
                        channel_oid = self.create_channels(
                            channel_path) or self.root_channel.get('oid')
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
                                truncate_to = 254 - \
                                    data['keywords'].count(',') * 2
                                data['keywords'] = data['keywords'][:truncate_to]

                            # lower transcoding priority
                            data['priority'] = 'low'
                            result = self.ms_client.api(
                                'medias/add', method='post', data=data)
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

                                self.migrate_slides(media)
                            else:
                                logger.error(f"Failed to upload media: {presentation_id}")
                                self.failed.append(presentation_id)

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
        subfolders = channel_path.split(
            self.mediasite_userfolder)[1].split('/')
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
            base_path = self.root_channel.get('title')
            parent_channel_title = self.root_channel.get('parent_title')
            while parent_channel_title:
                base_path = f'{parent_channel_title}/{base_path}'
                parent_channel = self.ms_client.api('channels/get', method='get', params={'title': parent_channel_title})
                parent_channel_title = parent_channel['info'].get('parent_title')
            target = f'mscpath-{base_path}/{self.unknown_users_channel_title}/{subfolders_path}'
        return target

    @lru_cache
    def _get_user_id(self, username):
        users = self.ms_client.api('users/', method='get', params={'search': username, 'search_in': 'username'})['users']
        # this is search, so multiple users may share username prefixes; find the exact match
        for user in users:
            if user['username'] == username:
                return user['id']

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
                        logger.info(
                            f'Granting permission to own a personal channel to user with id {user_id}')
                        data = {
                            'type': 'user',
                            'id': user_id,
                            'can_have_personal_channel': 'True',
                            'can_create_media': 'True',
                        }
                        result = self.ms_client.api(
                            'perms/edit/', method='post', data=data)
                        return self.get_user_channel_oid(user_id=user_id)
                    else:
                        logger.error(
                            f'Failed to get user channel for {key}={val} / Error: {error}')
            else:
                logger.error(f'Failed to get user channel: unknown error {result}')

    def find_folder_path(self, folder_id, folders=None, path=''):
        if folders is None:
            folders = self.mediasite_folders

        for folder in folders:
            if folder['Id'] == folder_id:
                path += self.find_folder_path(folder['ParentFolderId'], folders, path)
                path += '/' + folder['Name']
                return path
        return ''

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

    def search_mediasite_id_in_redirections(self, mediasite_id):
        # it is much faster to lookup the local redirections file than to perform an API request
        for from_url, to_url in self.redirections.items():
            if mediasite_id in from_url:
                oid = to_url.split('/')[4]
                return oid

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

    def migrate_composites_videos(self):
        total_composite = len(self.composites_medias)
        logger.info(f'Merging and migrating {total_composite} composite videos')

        self.download_composites_videos()

        for index, media in enumerate(self.composites_medias):
            self.processed_count += 1
            if sys.stdout.isatty():
                utils.print_progress_string(index, total_composite, title='Uploading composite')

            media_data = media.get('data', {})
            presentation_id = json.loads(media_data.get('external_data', {})).get('Id')
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
        logger.info(
            f'Downloading composite videos into {self.composites_folder}.')
        if self.compositor is None:
            self.compositor = VideoCompositor(self.config, self.dl_session, self.mediasite_auth)

        for i, v_composite in enumerate(self.composites_medias):
            utils.print_progress_string(i, len(self.composites_medias), title='Downloading composite')

            data = v_composite.get('data', {})
            presentation_id = json.loads(data.get('external_data', {})).get('Id')
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

    def get_presentation_url(self, presentation_id):
        presentation = self.get_presentation_by_id(presentation_id)
        if presentation:
            return presentation.get('#Play', {}).get('target')

    @lru_cache
    def get_presentation_by_id(self, presentation_id):
        for f in self.mediasite_folders:
            for presentation in f['Presentations']:
                if presentation['Id'] == presentation_id:
                    return presentation

    @lru_cache
    def get_presentation_parent_folder(self, presentation_id):
        for folder in self.mediasite_folders:
            for presentation in folder['Presentations']:
                if presentation['Id'] == presentation_id:
                    return folder

    @lru_cache
    def get_folder_by_path(self, path):
        for f_id, f_path in self.all_paths.items():
            if f_path == path:
                return self.get_folder_by_id(f_id)

    @lru_cache
    def get_folder_by_id(self, folder_id):
        for f in self.mediasite_folders:
            if f['Id'] == folder_id:
                return f

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
        name = folder['Name']
        most_recent_time = None
        most_recent_catalog = None
        for c in folder['Catalogs']:
            catalog_date = mediasite_utils.parse_mediasite_date(
                c['CreationDate'])
            if most_recent_time is None or catalog_date > most_recent_time:
                most_recent_time = catalog_date
                most_recent_catalog = c
        if most_recent_catalog is not None:
            name = most_recent_catalog['Name']
            logger.debug(f'Overriding channel name with the most recent catalog name {name}')
        return name

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
        # turn path 'a/b/c/d' into list ['/a/b/c/d', '/a/b/c', '/a/b', '/a']
        tree_list = list()
        for i in range(len(tree) + 1):
            if tree:
                path = '/' + '/'.join(tree)
                if self.channel_has_catalog(path):
                    logger.debug(
                        f'Parent folder {path} has a catalog, making complete path {channel_path} listed')
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
                folder_id = folder['Id']
                external_data = json.dumps({
                    'id': folder['Id'],
                    'name': folder['Name'],
                    'catalogs': folder['Catalogs']},
                    indent=2)
                for c in folder['Catalogs']:
                    urls.append(c['CatalogUrl'])
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
                    self.redirections[url] = self.get_full_ms_url(
                        f'/permalink/{new_oid}/iframe/?header=no')
            oid = new_oid

        # last item in list is the final channel, return it's oid
        # because he will be the parent of the video
        return oid

    def _create_channel(self, parent_channel, channel_title, is_unlisted, original_path, external_ref=None, external_data=None):
        logger.debug(
            f'Creating channel {channel_title} with parent {parent_channel} / is_unlisted : {is_unlisted}')
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

    def migrate_slides(self, media):
        presentation_id = json.loads(media['data']['external_data'])['Id']
        media_slides = media['data'].get('slides')
        nb_slides_uploaded, nb_slides = 0, 0

        if media_slides and media['data']['detect_slides'] != 'yes':
            if not media_slides.get('SlideDetails'):
                media['data']['detect_slides'] = 'yes'
                return 0, 0
            logger.debug(f"Migrating slides for medias: {media['ref']['media_oid']}")

            slides_dir = self.slides_folder / presentation_id
            nb_slides = media_slides.get('Length')
            nb_slides_uploaded = self._upload_slides(media, slides_dir)
            self.uploaded_slides_count += nb_slides_uploaded
        else:
            logger.debug(f"Media {media['ref']['media_oid']} has slides binded to video (no timecode). \
                          Detect slides will be lauched in Mediaserver.")

        logger.debug(
            f"{nb_slides_uploaded} uploaded (amongs {nb_slides} slides) for media {media['ref']['media_oid']}")

        return nb_slides_uploaded, nb_slides

    def _upload_slides(self, media, slides_dir):
        media_oid = media['ref']['media_oid']
        media_slides_details = media['data']['slides']['SlideDetails']
        nb_slides_uploaded = 0

        if self.slide_annot_type is None:
            self.slide_annot_type = self._get_annotation_type_id(media_oid, annotation_type='slide')

        logger.debug(f'Uploading slides for medias: {media_oid}')

        slides_paths = sorted([path for path in slides_dir.iterdir()])
        for i, slide_path in enumerate(slides_paths):
            details = {
                'oid': media_oid,
                'time': media_slides_details[i].get('TimeMilliseconds'),
                'title': media_slides_details[i].get('Title'),
                'content': media_slides_details[i].get('Content'),
                'type': self.slide_annot_type
            }
            success = self._add_annotation_safe(details, slide_path)
            if success:
                nb_slides_uploaded += 1
            else:
                self.skipped_slides_count += 1

        return nb_slides_uploaded

    def _get_annotation_type_id(self, media_oid, annotation_type):
        annot_type_id = int()

        result = self.ms_client.api('annotations/types/list/', method='get', params={'oid': media_oid})
        if result.get('success'):
            for annot_type_res in result.get('types'):
                if annot_type_res.get('slug') == annotation_type:
                    annot_type_id = annot_type_res.get('id')

        return annot_type_id

    def _add_annotation_safe(self, data, path=None):
        media_oid = data['oid']
        arguments = {
            'method': 'post',
            'data': data
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
        already_up = not (result.get('success')
                          and len(result.get('slides')) == 0)
        if already_up:
            logger.warning(f'Slides already uploaded for media {media_oid}')

        return already_up

    def _send_audio_thumb(self, media_oid):
        file = open('mediasite_migration_scripts/files/utils/audio.jpg', 'rb')
        result = self.ms_client.api('medias/edit', method='post', data={'oid': media_oid}, files={'thumb': file})
        file.close()
        return result.get('success')

    def add_chapters(self, media_oid, chapters):
        logger.debug(f'Adding chapters for media {media_oid}')

        ok = True
        if self.chapters_annot_type is None:
            self.chapters_annot_type = self._get_annotation_type_id(media_oid, annotation_type='chapter')

        for c in chapters:
            data = {
                'oid': media_oid,
                'title': c.get('Title'),
                'time': c.get('Position'),
                'type': self.chapters_annot_type
            }
            success = self._add_annotation_safe(data)
            if not success:
                self.skipped_chapters_count += 1

        return ok

    def add_presentation_redirection(self, presentation_id, oid):
        mediasite_presentation_url = self.get_presentation_url(presentation_id)
        if mediasite_presentation_url:
            self.redirections[mediasite_presentation_url] = self.get_full_ms_url(f'/permalink/{oid}/iframe/')

    def to_mediaserver_keys(self):
        logger.debug('Matching Mediasite data to MediaServer keys mapping.')
        logger.debug(f'Whitelist: {self.config.get("whitelist")}')

        mediaserver_data = list()
        if hasattr(self, 'mediaserver_data'):
            mediaserver_data = self.mediaserver_data
        else:
            logger.info('No Mediaserver mapping. Generating mapping.')
            for index, folder in enumerate(self.mediasite_folders):
                utils.print_progress_string(index, len(
                    self.mediasite_folders), title='Mapping data and checking resources')

                folder_path = self.find_folder_path(
                    folder['Id'], self.mediasite_folders)
                if utils.is_folder_to_add(folder_path, config=self.config):
                    has_catalog = (len(folder.get('Catalogs', [])) > 0)
                    is_unlisted_channel = not has_catalog
                    for p in self.public_paths:
                        if folder_path.startswith(p):
                            is_unlisted_channel = False
                            break

                    for presentation in folder['Presentations']:
                        data = dict()
                        pid = presentation['Id']
                        # there is no use in checking if the video is available if we already processed it
                        if self.search_mediasite_id_in_redirections(pid):
                            continue

                        v_url, v_composites_urls, v_type = self._get_video_urls_and_type(presentation)
                        if v_url:
                            if self.config.get('external_data') is True:
                                ext_data = presentation
                            else:
                                ext_data = {key: presentation.get(key) for key in [
                                    'Id', 'Creator', 'PresentationAnalytics']}
                                for key in ['TotalViews', 'LastWatched']:
                                    ext_data[key] = ext_data['PresentationAnalytics'][key]

                            data = {
                                'title': presentation.get('Title', ''),
                                'channel_title': folder.get('Name', ''),
                                'channel_unlisted': is_unlisted_channel,
                                'creation': mediasite_utils.get_most_distant_date(presentation),
                                'validated': 'yes' if self._is_validated(presentation) else 'no',
                                'description': self.get_presentation_description(presentation),
                                'keywords': ','.join(presentation.get('TagList', [])),
                                'slug': 'mediasite-' + presentation.get('Id'),
                                'external_data': json.dumps(ext_data, indent=2, sort_keys=True),
                                'transcode': self._do_transcode(v_type, v_url),
                                'origin': 'mediasite-migration-client',
                                'detect_slides': 'yes' if v_type in ['computer_slides', 'composite_slides'] else 'no',
                                'slides': presentation.get('SlideDetailsContent'),
                                'layout': self._find_video_type_layout(v_type),
                                'chapters': self.get_chapters(presentation),
                                'video_type': v_type,
                                'file_url': v_url,
                                'composites_videos_urls': v_composites_urls
                            }
                            speaker_data = self.get_speaker_data(presentation.get('Owner'))
                            data.update(speaker_data)

                            if has_catalog:
                                channel_path_splitted = folder_path.split('/')
                                channel_path_splitted[-1] = data['channel_title']
                                channel_path = '/'.join(channel_path_splitted)
                            else:
                                channel_path = folder_path

                            if v_type == 'audio_only':
                                data['thumb'] = 'mediasite_migration_scripts/files/utils/audio.jpg'

                            mediaserver_data.append(
                                {'data': data, 'ref': {'channel_path': channel_path, 'folder_path': folder_path}})
                        else:
                            logger.warning(f"No valid video for presentation {presentation.get('Id')}, skipping")
                            self.skipped_count += 1
                            continue

        return mediaserver_data

    def _get_video_urls_and_type(self, presentation):
        v_url = v_composites_urls = None
        videos = order.order_and_filter_videos(presentation, self.dl_session)
        v_type, slides_source = self._find_video_type(presentation, videos)

        if v_type in ('composite_video', 'composite_slides'):
            v_composites_urls = self._get_composite_video_resources(presentation, videos)
            if v_composites_urls:
                v_url = 'local'
        else:
            if slides_source is not None:
                for v in videos:
                    if v.get('stream_type') == slides_source:
                        v_files = v.get('files')
                    break
            else:
                v_files = videos[0].get('files', [])
            v_url = self._find_file_to_upload(v_files)

        return v_url, v_composites_urls, v_type

    def _find_video_type(self, presentation, videos):
        video_type = str()
        slides_source = None
        videos_count = len(videos)

        if presentation.get('SlideDetailsContent') is not None:
            if videos_count > 1:
                video_type = 'composite_video'
            else:
                video_type = 'audio_slides'
                for f in videos[0].get('files'):
                    encoding_settings_parsed = f.get('encoding_settings', {})
                    if encoding_settings_parsed.get('video_codec'):
                        video_type = 'video_slides'
                        break

        elif presentation['SlideContent'].get('StreamType', '').startswith('Video'):
            slides = presentation['SlideContent']
            slides_source = slides['StreamType']
            slides_count = int(slides['Length'])
            if slides_count > 0:
                if videos_count > 1:
                    video_type = 'composite_slides'
                else:
                    video_type = 'computer_slides'
            else:
                video_type = 'audio_only'
                for f in videos[0].get('files', []):
                    encoding_settings_parsed = f.get('encoding_settings', {})
                    if encoding_settings_parsed.get('video_codec'):
                        video_type = 'computer_only'
                        break
        elif videos_count > 1:
            video_type = 'composite_video'
        else:
            video_type = 'audio_only'
            for f in videos[0].get('files', []):
                if f.get('encoding_infos', {}).get('video_codec'):
                    video_type = 'video_only'

        return video_type, slides_source

    def _find_file_to_upload(self, video_files):
        # FIXME: FIND BEST / HIGHEST QUALITY INSTEAD OF THE FIRST ONE
        video_url = ''
        for file in video_files:
            url = file['url']
            if file.get('format') == 'video/mp4':
                video_codec = file['encoding_infos'].get('video_codec')
                # video with audio only have no video_codec key
                if video_codec is None or video_codec == 'H264' and http.url_exists(url, self.dl_session):
                    video_url = url
                    break
            elif self.formats_allowed.get(file.get('format')):
                if http.url_exists(url, self.dl_session):
                    video_url = file['url']
                    break
        return video_url

    def _get_composite_video_resources(self, presentation, videos):
        composites_videos_resources = dict()
        pid = presentation['Id']
        slides = presentation.get('SlideDetailsContent')
        if slides is None:
            slides = presentation.get('SlideContent')
        slides_stream_type = slides.get('StreamType')

        for video in videos:
            name = video['stream_type']
            if name == slides_stream_type:
                name = 'Slides'
            for f in video['files']:
                if f['size_bytes'] > 0 and f['format'] == 'video/mp4':
                    url = f['url']
                    if (self.composites_folder / pid / 'mediaserver_layout.json').is_file() or http.url_exists(url, self.dl_session):
                        composites_videos_resources[name] = f['url']
                        break
        return composites_videos_resources

    def _find_video_type_layout(self, video_type):
        layout = str()

        if video_type == 'video_slides':
            layout = 'webinar'
        elif video_type in ['composite_video', 'composite_slides']:
            layout = 'composition'

        return layout

    def get_presentation_description(self, presentation):
        description = str()
        presenters = list()
        for p in presentation.get('Presenters'):
            presenter_name = p.get('DisplayName')
            if presenter_name:
                presenters.append(presenter_name)

        if presenters:
            description = f'Presenters: {", ".join(presenters)}'
        original_description = presentation.get('Description')
        if original_description:
            description += '\n<br>' + original_description

        return description

    def get_speaker_data(self, username):
        speaker_data = dict()
        for user in self.mediasite_users:
            if username == user['UserName']:
                speaker_data = {
                    'speaker_id': username,
                    'speaker_name': user.get('DisplayName'),
                    'speaker_email': user.get('Email').lower(),
                }
        return speaker_data

    def get_chapters(self, presentation):
        chapters = order.to_chapters(presentation['TimedEvents'])
        for chapter in chapters:
            videos = presentation['OnDemandContent']
            for video in videos:
                video_length = int(video['Length'])
                if chapter['Position'] > video_length:
                    return []
        return chapters

    def _do_transcode(self, video_type, video_url):
        do_transcode = 'no'
        if video_type in ['audio_only', 'composite_slides', 'composite_video']:
            do_transcode = 'yes'
        elif video_url.endswith('.wmv'):
            do_transcode = 'yes'

        return do_transcode

    def _is_validated(self, presentation):
        return presentation.get('Status') == 'Viewable' and presentation.get('Private') is False
