import logging
import json
import os
from decouple import config
import requests
import shutil

from mediasite_migration_scripts.lib import utils
from mediasite_migration_scripts.lib.mediaserver_setup import MediaServerSetup
from mediasite_migration_scripts.data_extractor import DataExtractor

logger = logging.getLogger(__name__)


class MediaTransfer():

    def __init__(self, mediasite_data=dict(), ms_log_level='WARNING'):
        self.mediasite_data = self._set_mediasite_data(mediasite_data)
        self.catalogs = self._set_catalogs()
        self.presentations = self._set_presentations()
        self.formats_allowed = self._set_formats_allowed()
        self.auth = (config('MEDIASITE_API_USER'), config('MEDIASITE_API_PASSWORD'))
        self.extractor = DataExtractor()
        self.dl_session = None

        self.ms_setup = MediaServerSetup(log_level=ms_log_level)
        self.ms_client = self.ms_setup.ms_client
        self.root_channel = self.get_root_channel()
        self.channels_created = list()

        self.mediaserver_data = self.to_mediaserver_keys()

    def upload_medias(self, max_videos=None):
        logger.debug(f'{len(self.mediaserver_data)} medias found for uploading.')
        logger.debug('Uploading videos')

        nb_medias_uploaded = 0
        for index, media in enumerate(self.mediaserver_data):
            if max_videos and index >= max_videos:
                break
            channel_path = media['ref']['channel_path']
            channel_oid = self.create_channel(channel_path)[-1]
            if not channel_oid:
                del media['data']['channel']
                channel_oid = media['data']['channel'] = self.root_channel

            result = self.ms_client.api('medias/add', method='post', data=media['data'])
            if result.get('success'):
                media['ref']['media_oid'] = result.get('oid')
                media['ref']['slug'] = result.get('slug')
                media['ref']['channel_oid'] = channel_oid

                self.migrate_slides(media)
                nb_medias_uploaded += 1
            else:
                logger.error(f'Failed to upload media: {media["title"]}')
            print(' ' * 50, end='\r')
            print(f'Uploading: [{nb_medias_uploaded} / {len(self.mediaserver_data)}] -- {int(100 * (nb_medias_uploaded / len(self.mediaserver_data)))}%', end='\r')

        print('')
        self.dl_session.close()

        return nb_medias_uploaded

    def remove_uploaded_medias(self):
        logger.debug('Deleting medias uploaded')

        medias = self.mediaserver_data
        nb_medias_removed = 0
        for i, m in enumerate(medias):
            nb_medias_removed += self.remove_media(m)
            print(f'Removing: [{i}/ {len(medias)}] -- {int(100 * (i/len(medias)))}%', end='\r')
        print('')
        return nb_medias_removed

    def remove_media(self, media=dict()):
        delete_completed = False
        nb_medias_removed = 0

        oid = media.get('ref', {}).get('oid')
        if oid:
            result = self.ms_client.api('medias/delete',
                                        method='post',
                                        data={'oid': oid, 'delete_metadata': True, 'delete_resources': True},
                                        ignore_404=True)
            if result:
                if result.get('success'):
                    logger.debug(f'Media {oid} removed.')
                    delete_completed = True
                    nb_medias_removed += 1
                else:
                    logger.error(f'Failed to delete media: {oid} / Error: {result.get("error")}')
            elif not result:
                logger.warning(f'Media not found in Mediaserver for removal with oid: {oid}. Searching with title.')
            else:
                logger.error(f'Something gone wrong when trying remove media {oid}')

        if not delete_completed:
            title = media['data']['title']
            media = self.ms_client.api('medias/get', method='get', params={'title': title}, ignore_404=True)
            while media and media.get('success'):
                oid = media.get('info').get('oid')
                result = self.ms_client.api('medias/delete',
                                            method='post',
                                            data={'oid': oid, 'delete_metadata': True, 'delete_resources': True},
                                            ignore_404=True)
                if result:
                    logger.debug(f'Media {oid} removed.')
                    nb_medias_removed += 1
                media = self.ms_client.api('medias/get', method='get', params={'title': title}, ignore_404=True)
            if media and not media.get('success'):
                logger.error(f'Failed to delete media: {oid} / Error: {result.get("error")}')

        return nb_medias_removed

    def get_root_channel(self):
        oid = str()
        try:
            with open('config.json') as f:
                config = json.load(f)
            oid = config.get('mediaserver_parent_channel')
        except Exception as e:
            logger.critical('No parent channel configured. See in config.json.')
            logger.debug(e)
            exit()

        root_channel = self.get_channel(oid)
        if not root_channel:
            logger.critical('Root channel does not exist. Please provide an existing channel oid in config.json')
            exit()
        return root_channel

    def get_channel(self, oid):
        channel = None
        channel = self.ms_client.api('channels/get', method='get', params={'oid': oid}, ignore_404=True)
        if channel and channel.get('success'):
            channel = channel.get('info')
        else:
            logger.error(f'Channel {oid} does not exist.')
        return channel

    def create_channel(self, channel_path):
        logger.debug(f'Creating channel path: {channel_path}')

        channels_oids = list()
        tree = channel_path.split('/')
        # path start with '/' , so tree[0] is a empty string
        tree.pop(0)

        channel = self._create_channel(self.root_channel.get('title'), tree[0])
        channels_oids.append(channel.get('oid'))
        logger.debug(f"Channel {channel.get('title')} created with oid {channel.get('oid')}")

        i = 1
        while channel.get('success') and i < len(tree):
            channel = self._create_channel(channels_oids[i - 1], tree[i])
            logger.debug(f'Channel oid: {channel.get("oid")}')
            channels_oids.append(channel.get('oid'))
            i += 1
        if i < len(tree):
            logger.error('Failed to construct channel path')
        return channels_oids

    def _create_channel(self, parent_channel, channel_title):
        logger.debug(f'Creating channel {channel_title} with parent {parent_channel}')
        channel = dict()

        already_created = False
        for c in self.channels_created:
            if channel_title == c.get('title'):
                logger.debug(f'Channel {channel_title} already created.')
                channel = c
                channel['success'] = True
                already_created = True
                break

        if not already_created:
            result = self.ms_client.api('channels/add', method='post', data={'title': channel_title, 'parent': parent_channel})
            if result and not result.get('success'):
                logger.error(f'Failed to create channel: {channel} / Error: {result.get("error")}')
            elif not result:
                logger.error(f'No response from API when creating channel: {channel}')
            else:
                channel = result
                self.channels_created.append({'title': channel_title, 'oid': channel.get('oid')})

        return channel

    def remove_channel(self, channel_title=None, channel_oid=None):
        ok = False
        if not channel_oid and not channel_title:
            logger.error('Request to remove channel but no channel provided (title or oid)')
        elif not channel_oid and channel_title:
            result = self.ms_client.api('channels/get', method='get', params={'title': channel_title}, ignore_404=True)
            if result:
                channel_oid = result.get('info', {}).get('oid')
            else:
                logger.error('Channel not found for removing')

        if channel_oid:
            result = self.ms_client.api('channels/delete', method='post', data={'oid': channel_oid, 'delete_content': 'yes', 'delete_resources': 'yes'})
            ok = result.get('success')
        else:
            logger.error(f'Something gone wrong when removing channel. Title: {channel_title} / oid: {channel_oid}')

        return ok

    def migrate_slides(self, media):
        media_oid = media['ref']['media_oid']
        media_slides = media['data']['slides']
        nb_slides_downloaded, nb_slides_uploaded, nb_slides = 0, 0, 0
        slides_in_video = False

        if media_slides:
            if media_slides['stream_type'] == 'Slide' and media_slides['details']:
                slides_dir = f"mediasite_migration_scripts/files/{media_oid}/slides"
                os.makedirs(slides_dir, exist_ok=True)
                nb_slides_downloaded, nb_slides_uploaded, nb_slides = self._migrate_slides(media)
            else:
                slides_in_video = True
                logger.debug(f'Media {media_oid} has slides in video (no timecode)')

        if not slides_in_video and nb_slides > 0:
            logger.debug(f"{nb_slides_downloaded} slides downloaded and {nb_slides_uploaded} uploaded (amongs {nb_slides} slides) for media {media['ref']['media_oid']}")
            shutil.rmtree(slides_dir)

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
            slide_dl_ok, path = self._download_slide(media_oid, url)
            if slide_dl_ok:
                nb_slides_downloaded += 1
            else:
                logger.error(f'Failed to download slide {i + 1} for media {media_oid}')

            details = {
                'oid': media_oid,
                'time': media_slides_details[i].get('TimeMilliseconds'),
                'title': media_slides_details[i].get('Title'),
                'content': media_slides_details[i].get('Content'),
                'type': 5
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
        path = f"mediasite_migration_scripts/files/{media_oid}/slides/{filename}"

        if os.path.exists(path):
            ok = True
        else:
            r = self.dl_session.get(url, auth=self.auth)
            if r.ok:
                with open(path, 'wb') as f:
                    f.write(r.content)
                ok = True
        return ok, path

    def to_mediaserver_keys(self):
        logger.debug('Matching Mediasite data to MediaServer keys mapping.')

        mediaserver_data = list()
        if hasattr(self, 'mediaserver_data'):
            mediaserver_data = self.mediaserver_data
        else:
            logger.debug('No Mediaserver mapping. Generating mapping.')
            for folder in self.mediasite_data:
                if self.extractor.is_folder_to_add(folder.get('path')):
                    for presentation in folder['presentations']:
                        presenters = str()
                        for p in presentation.get('other_presenters'):
                            presenters += p.get('display_name', '')

                        description_text = presentation.get('description', '')
                        description_text = description_text if description_text else ''
                        presenters = f'Presenters: {presenters}\n' if presenters else ''
                        description = f'{presenters}{description_text}'

                        v_type, slides_source = self._find_video_type(presentation)
                        v_url = self._find_file_to_upload(presentation, slides_source)

                        if v_url:
                            data = {
                                'title': presentation.get('title'),
                                'channel': folder.get('name'),
                                'creation': presentation.get('creation_date'),
                                'speaker_id': presentation.get('owner_username'),
                                'speaker_name': presentation.get('owner_display_name'),
                                'speaker_email': presentation.get('owner_mail').lower(),
                                'validated': 'yes' if presentation.get('published_status') else 'no',
                                'description': description,
                                'keywords': ','.join(presentation.get('tags')),
                                'slug': 'mediasite-' + presentation.get('id'),
                                'file_url': v_url,
                                'external_data': json.dumps(presentation, indent=2, sort_keys=True),
                                'transcode': 'no',
                                'origin': 'mediatransfer',
                                'detect_slides': 'yes' if v_type == 'computer_slides' or v_type == 'composite_slides' else 'no',
                                'layout': 'webinar' if v_type == 'computer_slides' else 'video',
                                'slides': presentation.get('slides'),
                                'video_type': v_type
                            }
                            mediaserver_data.append({'data': data, 'ref': {'channel_path': folder.get('path')}})
                        else:
                            logger.debug(f"No valid url for presentation {presentation.get('id')}")
                            continue
        return mediaserver_data

    def _find_video_type(self, presentation):
        video_type = str()
        slides_source = None
        if presentation.get('slides'):
            if presentation.get('slides').get('details'):
                video_type = 'video_slides_details'
            elif presentation.get('slides').get('stream_type').startswith('Video'):
                slides_source = presentation.get('slides').get('stream_type')
                video_type = 'computer_slides'
        else:
            video_type = 'video_only'

        return video_type, slides_source

    def _find_file_to_upload(self, presentation, slides_source=None):
        video_files = presentation.get('videos')[0]['files']

        if slides_source:
            for v in presentation.get('videos'):
                if v.get('stream_type') == slides_source:
                    video_files = v.get('files')
                    break

        video_url = str()
        for v in video_files:
            if v.get('format') == 'video/mp4':
                video_url = v['url']
                break
            elif self.formats_allowed.get(v.get('format')):
                video_url = v['url']
                break
            else:
                logger.debug(f"File format not handled: {v.get('format')}")
                break

        return video_url

    def _set_formats_allowed(self):
        formats = dict()
        try:
            with open('config.json') as f:
                config = json.load(f)
            formats = config.get('videos_formats_allowed')
        except Exception as e:
            logger.debug(e)
            logger.info('No config file. Settings set to default (all folder, all medias)')

        return formats

    def _set_catalogs(self):
        catalogs = list()
        for folder in self.mediasite_data:
            catalogs.extend(folder.get('catalogs'))
        return catalogs

    def _set_presentations(self):
        presentations = []
        for folder in self.mediasite_data:
            for p in folder['presentations']:
                presentations.append(p)
        return presentations
