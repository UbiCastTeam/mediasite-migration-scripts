import logging
import json
import os
import requests
import shutil
import sys


from mediasite_migration_scripts.ms_client.client import MediaServerClient
from mediasite_migration_scripts.utils import common as utils
from mediasite_migration_scripts.ms_client.client import MediaServerRequestError as MSReqErr
from mediasite_migration_scripts.video_compositor import VideoCompositor


logger = logging.getLogger(__name__)


class MediaTransfer():

    def __init__(self, config=dict(), mediasite_data=dict(), mediasite_users=dict(), unit_test=False, e2e_test=False, root_channel_oid=None):
        self.config = config
        self.mediasite_data = mediasite_data

        self.mediasite_auth = (self.config.get('mediasite_api_user'), self.config.get('mediasite_api_password'))
        self.dl_session = None
        self.compositor = None

        self.e2e_test = e2e_test
        self.unit_test = unit_test
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
        self.channels_created = list()
        self.slide_annot_type = None
        self.chapters_annot_type = None

        self.mediaserver_data = self.to_mediaserver_keys()
        self.users = self.to_mediaserver_users(mediasite_users)
        self.composites_videos = list()

    def upload_medias(self, max_videos=None):
        total_medias = len(self.mediaserver_data)
        logger.debug(f'{total_medias} medias found for uploading.')
        logger.debug('Uploading videos')
        print(' ' * 50, end='\r')

        for i, user in enumerate(self.users):
            user_id = self.create_user(user)
            user['id'] = user_id

        nb_medias_uploaded = 0
        attempts = 0
        while nb_medias_uploaded != total_medias and attempts < 10:
            attempts += 1
            if max_videos:
                total_medias = max_videos

            logger.debug(f'Attempt {attempts} for uploading medias.')
            if attempts > 1:
                nb_medias_left = total_medias - nb_medias_uploaded
                logger.debug(f'{nb_medias_left} medias left to upload.')

            for index, media in enumerate(self.mediaserver_data):
                print(f'Uploading: [{nb_medias_uploaded} / {len(self.mediaserver_data)}] -- {int(100 * (nb_medias_uploaded / len(self.mediaserver_data)))}%', end='\r')

                if max_videos and index >= max_videos:
                    break

                if not media.get('ref', {}).get('media_oid'):
                    try:
                        data = media.get('data', {})
                        presentation_id = json.loads(data.get('external_data', {})).get('id')

                        channel_path = media['ref'].get('channel_path')
                        if channel_path.startswith('/Mediasite Users'):
                            channel_oid = self.get_user_channel(data.get('speaker_email', ''))
                        else:
                            channel_oid = self.create_channels(channel_path, is_unlisted=data['channel_unlisted'])[-1]

                        if not channel_oid:
                            data['channel'] = self.root_channel.get('oid')
                        else:
                            data['channel'] = channel_oid

                        if data.get('video_type') == 'composite_video':
                            logger.info('Composite video !!!!!')
                            self.composites_videos.append(media)
                        else:
                            result = self.ms_client.api('medias/add', method='post', data=data)
                            if result.get('success'):
                                media['ref']['media_oid'] = result.get('oid')
                                media['ref']['slug'] = result.get('slug')
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

            self.download_composites_videos()

        print('')

        self.ms_client.session.close()
        if self.dl_session is not None:
            self.dl_session.close()

        return nb_medias_uploaded

    def compose_video(self, videos_urls, presentation_id):
        if self.compositor is None:
            self.compositor = VideoCompositor(self.config, self.dl_session, self.mediasite_auth)
        media_path = self.compositor.compose(videos_urls, presentation_id)
        return media_path

    def download_composites_videos(self):
        logger.info(f'Downloading composites videos.')

        all_ok = False
        medias_downloaded = 0
        videos_downloaded = 0
        for v_composite in self.composites_videos:
            data = v_composite.get('data', {})
            presentation_id = data.get('external_data', {}).get('id')
            logger.debug(f"Downloadind for presentation {presentation_id}")

            urls = data.get('videos_composites_urls', [])
            dl_ok = self.download_videos(urls)
            if dl_ok:
                medias_downloaded += 1
            else:
                logger.error(f'Failed to download composites videos for presentation {presentation_id}.')
        all_ok = (medias_downloaded == len(self.composites_videos))
        if all_ok:
            logger.info(f'Sucessfully downloaded all composites videos for all medias ({len(self.composites_videos)})')
        else:
            logger.error(f'Failed to download all composites videos: {medias_downloaded} / {len(self.composites_videos)} / ')
        return all_ok

    def download_videos(self, videos_urls):
        if self.compositor is None:
            self.compositor = VideoCompositor(self.config, self.dl_session, self.mediasite_auth)

        dl_ok = False
        dl_ok = self.compositor.download(videos_urls)

        return dl_ok

    def upload_local_file(self, file_path, data):
        logger.debug(f"Uploading local file (composite video) : {file_path}")

        result = self.ms_client.add_media(file_path=file_path, **data)
        return result

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
            logger.error(f'Channel {oid} does not exist.')

        return channel

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
            exit(1)

        root_channel = self.get_channel(oid)
        if not root_channel:
            logger.error('Root channel does not exist. Please provide an existing channel oid in config.json')
            sys.exit(1)
        return root_channel

    def get_user_channel(self, user_email):
        logger.debug(f'Getting user channel for user email {user_email}')
        channel_oid = str()

        result = self.ms_client.api('channels/personal/', method='get', params={'email': user_email}, ignore_404=True)
        if result and result.get('success'):
            channel_oid = result.get('oid')
        else:
            logger.error(f"Failed to get user channel for {user_email} / Error: {result.get('error')}")

        return channel_oid

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

    def create_channels(self, channel_path, is_unlisted=False):
        logger.debug(f'Creating channel path: {channel_path}')

        channels_oids = list()
        tree = channel_path.split('/')
        # path start with '/' , so tree[0] is a empty string
        tree.pop(0)
        channel = self._create_channel(self.root_channel.get('oid'), tree[0], is_unlisted=is_unlisted)
        channels_oids.append(channel.get('oid'))

        if not channel.get('already_created'):
            logger.debug(f"Channel oid {channel.get('oid')}")

        i = 1
        while channel.get('success') and i < len(tree):
            last_channel = (i == len(tree) - 1)
            channel = self._create_channel(parent_channel=channels_oids[i - 1], channel_title=tree[i], is_unlisted=last_channel and is_unlisted)
            channels_oids.append(channel.get('oid'))
            logger.debug(f'Channel oid: {channel.get("oid")}')
            i += 1

        if i < len(tree):
            logger.error('Failed to construct channel path')

        return channels_oids

    def _create_channel(self, parent_channel, channel_title, is_unlisted=False):
        logger.debug(f'Creating channel {channel_title} with parent {parent_channel} / is_unlisted : {is_unlisted}')
        channel = dict()

        for c in self.channels_created:
            if channel_title == c.get('title'):
                logger.debug(f'Channel {channel_title} already created.')
                channel = c
                channel['success'] = True
                channel['already_created'] = True
                if is_unlisted:
                    logger.debug(f'Channel edit: {channel_title}')
                    result = self.ms_client.api('perms/edit/default/', method='post', data={'oid': channel.get('oid'), 'unlisted': 'yes'}, ignore_404=True)
                    if result and not result.get('success'):
                        logger.error(f"Failed to edit channel {channel.get('oid')} / Error: {result.get('error')}")
                    elif not result:
                        logger.error(f'Attempt to edit a channel not created: {channel_title}')
                break

        if not channel.get('already_created'):
            data = {'title': channel_title, 'parent': parent_channel, 'unlisted': 'yes' if is_unlisted else 'no'}
            result = self.ms_client.api('channels/add', method='post', data=data)

            if result and not result.get('success'):
                logger.error(f'Failed to create channel: {channel} / Error: {result.get("error")}')
            elif not result:
                logger.error(f'No response from API when creating channel: {channel}')
            else:
                channel = result
                self.channels_created.append({'title': channel_title, 'oid': channel.get('oid')})

                if is_unlisted:
                    logger.debug(f"Channel {channel.get('oid')} unlisted : requesting channel edit")

                    result = self.ms_client.api('perms/edit/default/', method='post', data={'oid': channel.get('oid'), 'unlisted': 'yes'}, ignore_404=True)
                    if result and not result.get('success'):
                        logger.error(f"Failed to edit channel {channel.get('oid')} / Error: {result.get('error')}")
                    elif not result:
                        logger.error(f'Attempt to edit a channel not created: {channel_title}')

        return channel

    def migrate_slides(self, media):
        media_oid = media['ref'].get('media_oid')
        media_slides = media['data'].get('slides')
        nb_slides_downloaded, nb_slides_uploaded, nb_slides = 0, 0, 0

        if media_slides:
            if media_slides.get('stream_type') == 'Slide' and media_slides.get('details'):
                slides_dir = f'/tmp/mediasite_files/slides/{media_oid}'
                os.makedirs(slides_dir, exist_ok=True)
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
        path = f'/tmp/mediasite_files/{media_oid}/slides/{filename}'

        if os.path.exists(path):
            ok = True
        else:
            r = self.dl_session.get(url, auth=self.mediasite_auth)
            if r.ok:
                with open(path, 'wb') as f:
                    f.write(r.content)
                ok = r.ok

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
                    for presentation in folder['presentations']:
                        presenters = str()
                        for p in presentation.get('other_presenters'):
                            presenters += p.get('display_name', '')

                        description_text = presentation.get('description', '')
                        description_text = description_text if description_text else ''
                        presenters = f'Presenters: {presenters}' if presenters else ''
                        description = f'[{presenters}] \n<br/>{description_text}'

                        v_url = str()
                        v_composites_urls = list()
                        v_files = list()
                        videos = presentation.get('videos', [])
                        v_type, slides_source = self._find_video_type(presentation)
                        if v_type == 'composite_video' or v_type == 'composite_slides':
                            v_url = ''
                            for v in videos:
                                v_composites_urls.append(self._find_file_to_upload(v.get('files', [])))
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
                            logger.debug(f"Found file with handled format for presentation {presentation.get('id')}: {v_url} ")
                            has_catalog = len(folder.get('catalogs', [])) > 0
                            channel_name = folder['catalogs'][0].get('name') if has_catalog else folder.get('name')
                            ext_data = presentation if self.config.get('external_data') else {'id': presentation.get('id')}
                            data = {
                                'title': presentation.get('title'),
                                'channel_title': channel_name,
                                'channel_unlisted': not has_catalog,
                                'unlisted': 'yes' if not has_catalog else 'no',
                                'creation': presentation.get('creation_date'),
                                'speaker_id': presentation.get('owner_username'),
                                'speaker_name': presentation.get('owner_display_name'),
                                'speaker_email': presentation.get('owner_mail').lower(),
                                'validated': 'yes' if presentation.get('published_status') else 'no',
                                'description': description,
                                'keywords': ','.join(presentation.get('tags')),
                                'slug': 'mediasite-' + presentation.get('id'),
                                'external_data': json.dumps(ext_data, indent=2, sort_keys=True),
                                'transcode': 'yes' if v_type == 'audio_only' else 'no',
                                'origin': 'mediatransfer',
                                'detect_slides': 'yes' if v_type == 'computer_slides' or v_type == 'composite_slides' else 'no',
                                'layout': 'webinar' if v_type == 'video_slides' else 'video',
                                'slides': presentation.get('slides'),
                                'chapters': presentation.get('timed_events'),
                                'video_type': v_type,
                                'file_url': v_url,
                                'composites_videos_urls': v_composites_urls
                            }

                            if has_catalog:
                                channel_path_splitted = folder.get('path').split('/')
                                channel_path_splitted[-1] = channel_name
                                path = '/'.join(channel_path_splitted)
                            else:
                                path = folder.get('path')

                            if v_type == 'audio_only':
                                data['thumb'] = 'mediasite_migration_scripts/files/utils/audio.jpg'

                            mediaserver_data.append({'data': data, 'ref': {'channel_path': path}})
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

    def _find_file_to_upload(self, video_files):
        video_url = str()
        for f in video_files:
            if f.get('format') == 'video/mp4':
                video_url = f['url']
                break
            elif self.formats_allowed.get(f.get('format')):
                video_url = f['url']
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
