import logging
import json
import os

from mediasite_migration_scripts.lib import utils
from mediasite_migration_scripts.data_analyzer import DataAnalyzer
from mediasite_migration_scripts.lib.mediaserver_setup import MediaServerSetup


logger = logging.getLogger(__name__)


class MediaServerImportManager():
    def __init__(self, mediasite_data, log_level='WARNING'):
        self.mediasite_data = mediasite_data
        self.catalogs = self._set_catalogs()
        self.presentations = self._set_presentations()
        self.formats_allowed = self._set_formats_allowed()

        self.ms_setup = MediaServerSetup(log_level=log_level)
        self.ms_client = self.ms_setup.ms_client
        self.parent_channel = self.get_parent_channel()
        self.mediaserver_data = self.to_mediaserver_keys()

    def get_parent_channel(self, **kwargs):
        oid = str()
        try:
            with open('config.json') as f:
                config = json.load(f)
            oid = config.get('mediaserver_parent_channel')
        except Exception as e:
            logger.error('No parent channel configured. See in config.json.')
            logger.debug(e)
            exit()

        parent_channel = dict()
        parent_channel = self.ms_client.api('channels/get', method='get', params={'oid': oid})
        if parent_channel.get('success'):
            parent_channel = parent_channel.get('info')
        return parent_channel

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

    def to_mediaserver_keys(self):
        logger.debug('Matching Mediasite data to MediaServer keys mapping.')

        mediaserver_data = list()
        if hasattr(self, 'mediaserver_data'):
            mediaserver_data = self.mediaserver_data
        else:
            logger.debug('No data file found for Mediaserver mapping. Generating mapping.')
            for folder in self.mediasite_data:
                for presentation in folder['presentations']:
                    presenter = f"Primary presenter: {presentation['presenter_display_name']}" if presentation.get("presenter_display_name") else ''
                    other_presenters = '\nOther presenters:' if presentation.get('other_presenters') else ''
                    for other_p in presentation['other_presenters']:
                        if not other_p == presenter:
                            other_presenters += f", {other_p['display_name']}"
                    description_text = '' if presentation['description'] is None else f"\n{presentation['description']}"
                    description = f'{presenter}{other_presenters}{description_text}'

                    video_url = None
                    for v in presentation.get('videos')[0]['files']:
                        if self.formats_allowed.get('mp4') and v['format'] == 'video/mp4':
                            video_url = v['url']
                            break
                        elif self.formats_allowed.get('wmv') and v['format'] == 'video/x-ms-wmv':
                            video_url = v['url']
                            break
                    data = {
                        'title': presentation['title'],
                        'channel': self.parent_channel.get('oid'),
                        'creation': presentation['creation_date'],
                        'speaker_id': presentation['owner_username'],
                        'speaker_name': presentation['owner_display_name'],
                        'speaker_email': presentation['owner_mail'].lower(),
                        'validated': 'Yes' if presentation['published_status'] else 'No',
                        'description': description,
                        'keywords': ','.join(presentation['tags']),
                        'slug': 'mediasite-' + presentation['id'],
                        'file_url': video_url,
                        'external_data': json.dumps(presentation)
                    }
                    mediaserver_data.append({'data': data})
        return mediaserver_data

    def upload_medias(self, max_videos=None):
        logger.debug(f'len{self.mediaserver_data} medias found for uploading.')
        logger.debug('Uploading videos')

        for index, media in enumerate(self.mediaserver_data):
            if max_videos is not None and index >= max_videos:
                break
            print('Uploading videos:', index, '/', len(self.mediaserver_data), f'-- {int(100 * (index/len(self.mediaserver_data)))}%', end='\r')
            result = self.ms_client.api('medias/add', method='post', data=media['data'])
            if result.get('success'):
                media['ref'] = {'oid': result.get('oid'), 'slug': result.get('slug')}
            else:
                logger.error(f'Failed to upload media: {media["title"]}')

    def delete_uploaded_medias(self):
        logger.debug('Deleting medias uploaded')

        medias = self.mediaserver_data
        print(medias[0])
        print('')
        for i, m in enumerate(medias):
            print('Removing:', i, '/', len(medias), f'-- {int(100 * (i/len(medias)))}%', end='\r')
            oid = m.get('ref').get('oid')
            result = self.ms_client.api('medias/delete', method='post', data={'oid': oid, 'delete_metadata': True, 'delete_resources': True}, ignore_404=True)
            if result and not result.get('success'):
                logger.warning(f'Failed to delete media: {oid}')
            elif not result:
                logger.warning(f'Media not found in Mediaserver for removal: {oid}')

        return len(medias)
