from unittest import TestCase
import random
import os
import json
import logging

from mediasite_migration_scripts.import_manager import MediaServerImportManager
import tests.common as common


def setUpModule():
    print('-> ', __name__)

logger = common.set_logger(run_path=__name__)


class TestImportManager(TestCase):
    def setUp(self):
        super(TestImportManager)
        self.data = common.set_test_data()
        self.ms_import = MediaServerImportManager(data=self.data)

    def tearDown(self):
        self.ms_import.ms_client.session.close()

    def test_set_presentations(self):
        folder_index = random.randint(0, len(self.data) - 1)
        presentations_example = self.data[folder_index]['presentations']
        presentations = self.ms_import._set_presentations()
        for p in presentations_example:
            self.assertIn(p, presentations)

    def test_set_catalogs(self):
        test_catalog = self.data[0]['catalogs'][0]
        catalogs = self.ms_import._set_catalogs()
        self.assertIn(test_catalog, catalogs)

    def test_to_mediaserver_keys(self):
        folder_index = random.randint(0, len(self.data) - 1)
        i = 0
        while not self.data[folder_index].get('presentations') and i < 100:
            folder_index = random.randint(0, len(self.data) - 1)
        try:
            presentation_example = self.data[folder_index].get('presentations')[0]
        except IndexError:
            logger.error('Can not found presentations')
        except Exception as e:
            logger.error(e)
            raise AssertionError

        mediaserver_data = self.ms_import.to_mediaserver_keys()
        try:
            with open('tests/mediaserver_data_test.json', 'w') as f:
                json.dump(mediaserver_data, f)
        except Exception as e:
            logger.error(e)
            raise AssertionError

        found = False
        mediaserver_media = dict()
        for presentation in mediaserver_data:
            if presentation['title'] == presentation_example['title']:
                found = True
                mediaserver_media = presentation
                break

        self.assertTrue(found)

        self.assertEqual(mediaserver_media['title'], presentation_example['title'])
        self.assertEqual(mediaserver_media['creation'], presentation_example['creation_date'])
        self.assertEqual(mediaserver_media['speaker_id'], presentation_example['owner_username'])
        self.assertEqual(mediaserver_media['speaker_name'], presentation_example['owner_display_name'])
        self.assertEqual(mediaserver_media['speaker_name'], presentation_example['owner_display_name'])
        self.assertEqual(mediaserver_media['speaker_email'], presentation_example['owner_mail'])
        self.assertEqual(mediaserver_media['validated'], 'Yes' if presentation_example['published_status'] else 'No')
        self.assertEqual(mediaserver_media['keywords'], ','.join(presentation_example['tags']))
        self.assertEqual(mediaserver_media['slug'], 'mediasite-' + presentation_example['id'])
    
        self.assertIsNotNone(mediaserver_media['file_url'])
        self.assertEqual(mediaserver_media['external_data'], presentation_example)
        pass

    def test_upload_videos(self):
        pass