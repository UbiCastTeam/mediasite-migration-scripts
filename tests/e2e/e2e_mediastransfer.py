from unittest import TestCase
import random
import json
import logging
import sys
import os

from mediasite_migration_scripts.mediatransfer import MediaTransfer
from mediasite_migration_scripts.lib.mediaserver_setup import MediaServerSetup
import tests.common as common


test_channel = common.create_test_channel()
logger = logging.getLogger(__name__)


def setUpModule():
    print('-> ', __name__)


def tearDownModule():
    body = {'oid': test_channel.get('oid'), 'delete_resources': 'yes', 'delete_content': 'yes'}
    ms_client = MediaServerSetup().ms_client
    ms_client.api('channels/delete', method='post', data=body)
    ms_client.session.close()


class FakeOptions:
    verbose = True
    info = False


class TestMediaTransferE2E(TestCase):
    def setUp(self):
        super(TestMediaTransferE2E)
        self.mediasite_data = common.set_test_data()
        self.mediatransfer = MediaTransfer(self.mediasite_data, 'WARNING', test=True, root_channel_oid=test_channel.get('oid'))
        self.ms_client = self.mediatransfer.ms_client
        try:
            with open('tests/e2e/mediaserver_data_e2e.json') as f:
                self.mediaserver_data = json.load(f)
            self.mediatransfer.mediaserver_data = self.mediaserver_data
        except Exception as e:
            logger.debug(e)
            logger.critical("Test data corrupted")
            exit()

        fake_opt = FakeOptions()
        fake_opt.verbose = sys.argv[-1] == '-v' or sys.argv[-1] == '--verbose'
        common.set_logger(options=fake_opt)

        self.config = {}
        file = 'config.json'
        if os.path.exists(file):
            with open(file) as f:
                self.config = json.load(f)

    def tearDown(self):
        try:
            with open(common.MEDIASERVER_DATA_FILE, 'w') as f:
                json.dump(self.mediaserver_data, f)
        except Exception as e:
            logger.error(f'Failed to save mediaserver data file: {e}')

    def test_upload_medias(self):
        medias_examples = self.mediaserver_data
        self.mediatransfer.upload_medias()
        for m in medias_examples:
            data = m['data']
            result = self.ms_client.api('medias/get', method='get', params={'oid': m['ref']['media_oid'], 'full': 'yes'})
            self.assertTrue(result.get("success"))
            m_uploaded = result.get('info')
            keys_to_skip = ['file_url', 'creation', 'slug', 'api_key', 'slides', 'transcode', 'detect_slides', 'video_type']
            for key in data.keys():
                try:
                    self.assertEqual(data[key], m_uploaded.get(key))
                except AssertionError:
                    if key == 'channel':
                        self.assertEqual(data[key], m_uploaded.get('parent_title'))
                    elif key == 'speaker_name':
                        self.assertEqual(data[key], m_uploaded.get('speaker'))
                    elif key == 'validated':
                        self.assertTrue(m_uploaded.get(key)) if data[key] == 'yes' else self.assertFalse(m_uploaded.get(key))
                    elif key in keys_to_skip:
                        continue
                    else:
                        logger.error(f'[{key}] not equal')
                        raise

    def test_create_channel(self):
        paths_examples = ['/RATM', '/Bob Marley/Uprising', '/Pink Floyd/The Wall/Comfortably Numb', '/Tarentino/Kill Bill/Uma Turman/Katana']
        channels_examples_titles = ''.join(paths_examples).split('/')[1:]
        channels_created_oids = list()

        for p in paths_examples:
            channels_created_oids.extend(self.mediatransfer.create_channel(p))
        self.assertEqual(len(channels_created_oids), len(channels_examples_titles))

        for oid in channels_created_oids:
            result = self.ms_client.api('channels/get', method='get', params={'oid': oid}, ignore_404=True)
            self.assertIsNotNone(result)
            if result:
                self.assertIn(result.get('info').get('title'), channels_examples_titles)
            else:
                logger.error(f'Channel {oid} not found')

        longest_tree = paths_examples[-1].split('/')[1:]
        parent_oid = channels_created_oids[-len(longest_tree)]
        ms_tree = self.ms_client.api('channels/tree', method='get', params={'parent_oid': parent_oid})
        # we pop the parent channel
        longest_tree.pop(0)
        for c_example in longest_tree:
            found = False
            for index, c_created in enumerate(ms_tree.get('channels')):
                if c_example == c_created.get('title'):
                    found = True
                    c_found_index = index
                    break
            self.assertTrue(found)
            ms_tree = ms_tree.get('channels')[c_found_index]

    def test_migrate_slides(self):
        pass
