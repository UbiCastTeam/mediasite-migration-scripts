from unittest import TestCase
import random
import json
import logging
import sys
import os

from mediasite_migration_scripts.mediatransfer import MediaTransfer
import tests.common as common


test_channel = common.create_test_channel()
logger = logging.getLogger(__name__)


def setUpModule():
    print('-> ', __name__)


class FakeOptions:
    verbose = True
    info = False


class TestMediaTransfer(TestCase):

    def setUp(self):
        super(TestMediaTransfer)
        self.mediasite_data = common.set_test_data()
        self.mediatransfer = MediaTransfer(self.mediasite_data, 'WARNING')
        self.ms_client = self.mediatransfer.ms_client
        self.mediaserver_data = self.mediatransfer.mediaserver_data

        fake_opt = FakeOptions()
        fake_opt.verbose = sys.argv[-1] == '-v' or sys.argv[-1] == '--verbose'
        common.set_logger(options=fake_opt)

        self.config = {}
        file = 'config.json'
        if os.path.exists(file):
            with open(file) as f:
                self.config = json.load(f)

    def tearDown(self):
        self.ms_client.session.close()
        try:
            with open(common.MEDIASERVER_DATA_FILE, 'w') as f:
                json.dump(self.mediaserver_data, f)
        except Exception as e:
            logger.error(f'Failed to save mediaserver data file: {e}')

    def test_set_presentations(self):
        folder_index = random.randrange(len(self.mediasite_data))
        presentations_example = self.mediasite_data[folder_index]['presentations']
        presentations = self.mediatransfer._set_presentations()
        for p in presentations_example:
            self.assertIn(p, presentations)

    def test_set_catalogs(self):
        len_catalogs = 0
        for folder in self.mediasite_data:
            len_catalogs += len(folder.get('catalogs', []))
        catalogs = self.mediatransfer._set_catalogs()
        self.assertEqual(len_catalogs, len(catalogs))

    def test_to_mediaserver_keys(self):
        try:
            presentation_example = self.mediasite_data[0].get('presentations')[0]
        except IndexError:
            logger.error('Can not found presentations')
        except Exception as e:
            logger.error(e)

        mediaserver_data = self.mediatransfer.to_mediaserver_keys()
        try:
            with open('tests/mediaserver_data_test.json', 'w') as f:
                json.dump(mediaserver_data, f)
        except Exception as e:
            logger.error(e)

        self.assertEqual(mediaserver_data[0]['data']['title'], presentation_example['title'])
        self.assertEqual(mediaserver_data[0]['data']['creation'], presentation_example['creation_date'])
        self.assertEqual(mediaserver_data[0]['data']['speaker_id'], presentation_example['owner_username'])
        self.assertEqual(mediaserver_data[0]['data']['speaker_name'], presentation_example['owner_display_name'])
        self.assertEqual(mediaserver_data[0]['data']['speaker_name'], presentation_example['owner_display_name'])
        self.assertEqual(mediaserver_data[0]['data']['speaker_email'], presentation_example['owner_mail'])
        self.assertEqual(mediaserver_data[0]['data']['validated'], 'yes' if presentation_example['published_status'] else 'no')
        self.assertEqual(mediaserver_data[0]['data']['keywords'], ','.join(presentation_example['tags']))
        self.assertEqual(mediaserver_data[0]['data']['slug'], 'mediasite-' + presentation_example['id'])

        self.assertIsNotNone(mediaserver_data[0]['data']['file_url'])
        self.assertEqual(json.loads(mediaserver_data[0]['data']['external_data']), presentation_example)
