from unittest import TestCase
import random
import json
import logging

from mediasite_migration_scripts.import_manager import MediaServerImportManager
import tests.common as common


def setUpModule():
    print('-> ', __name__)


class TestImportManager(TestCase):
    def setUp(self):
        super(TestImportManager)
        self.data = common.make_test_data()
        self.ms_import = MediaServerImportManager(self.data)

    def test_set_presentations(self):
        folder_index = random.randint(0, len(self.data) - 1)
        presentations_example = self.data[folder_index]['presentations']
        presentations = self.ms_import._set_presentations()
        for p in presentations_example:
            self.assertIn(p, presentations)

    def test_set_mp4(self):
        folder_index = random.randint(0, len(self.data) - 1)
        pres_index = random.randint(0, len(self.data[folder_index]['presentations']) - 1)
        presentation_example = self.data[folder_index]['presentations'][pres_index]
        videos_example = presentation_example['videos']
        if len(videos_example) < 2:
            for f in videos_example[0]['files']:
                if f['format'] == 'video/mp4':
                    item = {'presentation_id': presentation_example['id'], 'video_url': f['url']}
                    self.assertIn(item, self.ms_import._set_mp4_urls())
                    break
