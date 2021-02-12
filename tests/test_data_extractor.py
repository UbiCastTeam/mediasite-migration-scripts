from unittest import TestCase
import json
import logging

from mediasite_migration_scripts.data_analyzer import DataAnalyzer
from mediasite_migration_scripts.data_extractor import DataExtractor

class TestDataExtractor(TestCase):
    folders_whitelist = []
    analyzer = object()
    extractor = object()

    def setUp(self):
        super(TestDataExtractor)
        self.extractor = DataExtractor()
        try:
            data = []
            with open('data.json') as f:
                data = json.load(f)
            self.analyzer = DataAnalyzer(data)
        except Exception as e:
            logging.error('No data to analyse, or data is corrupted.')
            logging.debug(e)

    def _check_whitelisting(self, folders):
        self.folders_whitelist
        for folder in folders:
            for fw in self.folders_whitelist:
                if not folder['path'].find(fw):
                    return False
        return True

    def _check_no_duplicate(self, folders):
        seen = {}
        for folder in self.analyzer.folders:
            for x in folder['presentations']:
                x = x['id']
                if x not in seen:
                    seen[x] = 1
                else:
                    if seen[x] > 1:
                        return False
        return True

    def _check_encoding_infos(self, folders):
        no_encoding_settings = list()
        for folder in folders:
            for presentation in folder['presentations']:
                for video in presentation['videos']:
                    for file in video['files']:
                        if file['format'] == 'video/mp4':
                            if not file.get('encoding_infos'):
                                no_encoding_settings.append(file)
                            elif file['encoding_infos'].get('video_codec'):
                                if file['encoding_infos'].get('video_codec') == 'AVC':
                                    return False
                            elif file['encoding_infos'].get('audio_codec'):
                                if file['encoding_infos'].get('audio_codec') == 'AACL':
                                    return False
        print(f'No encoding infos for {len(no_encoding_settings)} files')