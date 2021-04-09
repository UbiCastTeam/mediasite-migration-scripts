from unittest import TestCase
import json
import logging
import sys

from mediasite_migration_scripts.mediatransfer import MediaTransfer
from mediasite_migration_scripts.ms_client.client import MediaServerClient
import tests.common as common

logger = logging.getLogger(__name__)

config = {}
file = 'config.json'
try:
    with open(file) as f:
        config = json.load(f)
except Exception as e:
    logger.error('Failed to parse config file.')
    logger.debug(e)
    sys.exit(1)

ms_test_utils = common.MediaServerTestUtils(config)
test_channel = ms_test_utils.create_test_channel()
ms_client = ms_test_utils.ms_client


def setUpModule():
    print('-> ', __name__)


def tearDownModule():
    body = {'oid': test_channel.get('oid'), 'delete_resources': 'yes', 'delete_content': 'yes'}
    ms_client.api('channels/delete', method='post', data=body)
    ms_client.session.close()


class TestMediaTransferE2E(TestCase):
    def setUp(self):
        super().setUp()
        self.mediasite_data = common.set_test_data()
        self.mediatransfer = MediaTransfer(self.mediasite_data, config=config, e2e_test=True, root_channel_oid=test_channel.get('oid'))
        self.ms_client = ms_client
        try:
            with open('tests/e2e/mediaserver_data_e2e.json') as f:
                self.mediaserver_data = json.load(f)
            self.mediatransfer.mediaserver_data = self.mediaserver_data
        except Exception as e:
            logger.debug(e)
            logger.error('Test data corrupted')
            exit(1)

        common.set_logger(verbose=True)

    def tearDown(self):
        super().tearDown()
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
                        channel_title = self.mediatransfer.get_channel(oid=data['channel']).get('title')
                        self.assertEqual(channel_title, m_uploaded.get('parent_title'))
                    elif key == 'speaker_name':
                        self.assertEqual(data[key], m_uploaded.get('speaker'))
                    elif key == 'validated':
                        self.assertTrue(m_uploaded.get(key)) if data[key] == 'yes' else self.assertFalse(m_uploaded.get(key))
                    elif key in keys_to_skip:
                        continue
                    else:
                        logger.error(f'[{key}] not equal')
                        raise
            nb_slides, nb_slides_uploaded = self.nb_slides_uploaded(m)
            self.assertEqual(nb_slides, nb_slides_uploaded)

    def test_create_channel(self):
        paths_examples = ['/RATM', '/Bob Marley/Uprising', '/Pink Floyd/The Wall/Comfortably Numb', '/Tarentino/Kill Bill/Uma Turman/Katana']
        channels_examples_titles = ''.join(paths_examples).split('/')[1:]
        channels_created_oids = list()

        for p in paths_examples:
            channels_created_oids.extend(self.mediatransfer.create_channels(p))
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

    def nb_slides_uploaded(self, media):
        nb_slides = len(media['data']['slides']['urls'])
        nb_slides_uploaded = int()
        result = self.ms_client.api('annotations/slides/list/', method='get', params={'oid': media['ref'].get('media_oid')}, ignore_404=True)
        if result:
            nb_slides_uploaded = len(result.get('slides'))
        else:
            logger.error('No slides found')
            raise AssertionError

        return nb_slides, nb_slides_uploaded
