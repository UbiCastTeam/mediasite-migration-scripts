import logging
import json

from mediasite_migration_scripts.data_analyzer import DataAnalyzer
from mediasite_migration_scripts.lib.mediaserver_setup import MediaServerSetup


class MediaServerImportManager():
    def __init__(self, data, formats_allowed=dict(), log_level='WARNING'):
        self.mediasite_data = data
        self.catalogs = self._set_catalogs()
        self.presentations = self._set_presentations()
        self.formats_allowed = self._set_formats_allowed()

        self.ms_setup = MediaServerSetup(log_level=log_level)
        self.ms_client = self.ms_setup.ms_client
        self.parent_channel = self.get_parent_channel(oid='c126193efa3a9ielcoe6')
        self.mediaserver_data = self.to_mediaserver_keys()

    def get_parent_channel(self, **kwargs):
        parent_channel = dict()
        parent_channel = self.ms_client.api('channels/get', method='get', params={**kwargs})
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
            logging.debug(e)
            logging.info('No config file. Settings set to default (all folder, all medias)')
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
        logging.debug('Matching Mediasite data to MediaServer keys mapping.')
        if hasattr(self, 'mediaserver_data'):
            return self.mediaserver_data

        mediaserver_data = list()
        for folder in self.mediasite_data:

            for presentation in folder['presentations']:
                presenter = None
                presenter = f"Primary presenter: {presentation['presenter_display_name']}" if presentation.get("presenter_display_name") else ''
                other_presenters = '\nOther presenters' if presentation.get('other_presenters') else ''
                for p in presentation['other_presenters']:
                    other_presenters += f", {p['display_name']}"
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

                mediaserver_data.append({
                    'title': presentation['title'],
                    'channel': self.parent_channel.get('oid'),
                    'creation': presentation['creation_date'],
                    'speaker_id': presentation['owner_username'],
                    'speaker_name': presentation['owner_display_name'],
                    'speaker_email': presentation['owner_mail'],
                    'validated': 'Yes' if presentation['published_status'] else 'No',
                    'description': description,
                    'keywords': ','.join(presentation['tags']),
                    'slug': 'mediasite-' + presentation['id'],
                    'file_url': video_url,
                    'external_data': presentation
                })
        return mediaserver_data

    def upload_videos(self):
        i = 0
        for v in self.mediaserver_data:
            self.ms_client.api('medias/add', method='post', data=v)
            i += 1
            if i > 1:
                break

    def delete_uploaded_videos(self):
        logging.debug('Getting all videos uploaded oids')
        videos = list()
        i = 0
        for v in self.mediaserver_data:
            print(i, '/', len(self.mediaserver_data), f'{int(100 * (i/len(self.mediaserver_data)))}%', end='\r')
            video = self.ms_client.api('medias/get', method='get', params={'title': v['title']}, ignore_404=True)
            if video:
                videos.append(video)
            i += 1
        print(f'Found {len(videos) } videos uploaded')

        logging.debug('Deleting videos uploaded')
        print('Deleting videos uploaded')
        i = 0
        for v in videos:
            print(i, '/', len(videos), f'{int(100 * (i/len(videos)))}%', end='\r')
            oid = v.get('info').get('oid')
            result = self.ms_client.api('medias/delete', method='post', data={'oid': oid, 'delete_metadata': True, 'delete_resources': True}, ignore_404=True)
            if result and not result.get('success'):
                logging.warning(f'Failed to delete video: {oid}')
            elif not result:
                logging.warning(f'Video not found in Mediaserver for removal: {oid}')
            i += 1
