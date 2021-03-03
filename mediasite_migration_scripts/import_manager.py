import logging

from mediasite_migration_scripts.data_analyzer import DataAnalyzer
from mediasite_migration_scripts.lib.mediaserver_setup import MediaServerSetup


class MediaServerImportManager():
    def __init__(self, data, catalogs, formats_allowed=dict(), log_level='WARNING'):
        self.mediasite_data = data
        self.catalogs = catalogs
        self.presentations = self._set_presentations()
        self.videos = self._set_mp4_urls()
        self.formats_allowed = {
            "video/mp4": formats_allowed.get('mp4'),
            "video/x-ms-wmv": formats_allowed.get('wmv')
        } if formats_allowed else {}

        self.mediaserver_data = self.to_mediaserver_keys(self.mediasite_data)
        self.ms_setup = MediaServerSetup(log_level=log_level)
        self.ms_client = self.ms_setup.ms_client

    def _set_presentations(self):
        presentations = []
        for folder in self.mediasite_data:
            for p in folder['presentations']:
                presentations.append(p)
        return presentations

    def _set_mp4_urls(self):
        mp4_urls = list()
        for presentation in self.presentations:
            if not DataAnalyzer.has_multiple_videos(presentation):
                for file in presentation['videos'][0]['files']:
                    if file['format'] == 'video/mp4':
                        mp4_urls.append({'title': presentation['title'], 'file_url': file['url']})
                        break
        return mp4_urls

    def to_mediaserver_keys(self, mediasite_data):
        mediaserver_data = list()
        for folder in self.mediasite_data:
            in_catalog = False
            for c in folder['catalogs']:
                if c in self.catalogs:
                    in_catalog = True
                    break
            if in_catalog:
                for presentation in folder['presentations']:
                    presenters = presentation["presenter_display_name"]
                    # presenters += '\n' + ', '.join(presentation['other_presenters']) if presentation['other_presenters'] else ''
                    description = '' if presentation['description'] is None else presentation['description']
                    description += presenters

                    mediaserver_data = {
                        'title': presentation['title'],
                        'creation': presentation['creation_date'],
                        'speaker_id': presentation['owner_username'],
                        'speaker_name': presentation['owner_display_name'],
                        'speaker_email': presentation['owner_mail'],
                        'validated': 'Yes' if presentation['published_status'] else 'No',
                        'description': description,
                        'keywords': ','.join(presentation['tags']),
                        'slug': presentation['url'],
                        'external_data': presentation
                    }
        return mediaserver_data

    def upload_videos(self):
        i = 0
        for v in self.videos:
            self.ms_client.api('medias/add', method='post', data=v)
            i += 1
            if i > 3:
                break

    def delete_uploaded_videos(self):
        logging.debug('Getting all videos uploaded oids')
        videos = list()
        i = 0
        for v in self.videos:
            print(i, '/', len(self.videos), f'{int(100 * (i/len(self.videos)))}%', end='\r')
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
