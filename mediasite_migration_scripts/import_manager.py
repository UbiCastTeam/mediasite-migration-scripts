
from mediasite_migration_scripts.data_analyzer import DataAnalyzer
from mediasite_migration_scripts.lib.mediaserver_setup import MediaServerSetup


class MediaServerImportManager():
    def __init__(self, data):
        self.all_data = data
        self.presentations = self._set_presentations()
        self.videos_urls = self._set_mp4_urls()
        self.ms_client = MediaServerSetup()

    def _set_presentations(self):
        presentations = []
        for folder in self.all_data:
            for p in folder['presentations']:
                presentations.append(p)
        return presentations

    def _set_mp4_urls(self):
        mp4_urls = list()
        for presentation in self.presentations:
            if not DataAnalyzer.has_multiple_videos(presentation):
                for file in presentation['videos'][0]['files']:
                    if file['format'] == 'video/mp4':
                        mp4_urls.append(file['url'])
                        break
        return mp4_urls

    def upload_videos(self):
        pass