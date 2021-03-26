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
    body = {'oid': test_channel.get('oid'), 'delete_resources': True, 'delete_content': True}
    ms_client = MediaServerSetup().ms_client
    ms_client.api('channels/delete', method='post', data=body)
    ms_client.session.close()

class FakeOptions:
    verbose = True

class TestMediaTransfer(TestCase):

    def setUp(self):
        super(TestMediaTransfer)
        self.mediasite_data = common.set_test_data()
        self.mediatransfer = MediaTransfer(self.mediasite_data, 'WARNING')
        self.mediatransfer.root_channel = self.mediatransfer.get_channel(oid=test_channel.get('oid'))
        self.ms_client = self.mediatransfer.ms_client
        self.mediaserver_data = self.mediatransfer.mediaserver_data

        fake_opt = FakeOptions()
        fake_opt.verbose = sys.argv[-1] == '-v' or sys.argv[-1] == '--verbose'
        common.set_logger(option=fake_opt)

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
        test_catalog = self.mediasite_data[0]['catalogs'][0]
        catalogs = self.mediatransfer._set_catalogs()
        self.assertIn(test_catalog, catalogs)

    def test_to_mediaserver_keys(self):
        folder_index = random.randrange(len(self.mediasite_data))
        i = 0
        while not self.mediasite_data[folder_index].get('presentations') and i < 100:
            folder_index = random.randint(0, len(self.mediasite_data) - 1)
            i += 1

        try:
            presentation_example = self.mediasite_data[folder_index].get('presentations')[0]
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

        found = False
        mediaserver_media = dict()
        for media in mediaserver_data:
            if presentation_example['title'] == media['data']['title'] :
                found = True
                mediaserver_media = media['data']
                break
        for folder in self.config.get('whitelist'):
            if folder not in self.mediasite_data[folder_index]['path']:
                found = True
        self.assertTrue(found)

        if mediaserver_media:
            self.assertEqual(mediaserver_media['title'], presentation_example['title'])
            self.assertEqual(mediaserver_media['creation'], presentation_example['creation_date'])
            self.assertEqual(mediaserver_media['speaker_id'], presentation_example['owner_username'])
            self.assertEqual(mediaserver_media['speaker_name'], presentation_example['owner_display_name'])
            self.assertEqual(mediaserver_media['speaker_name'], presentation_example['owner_display_name'])
            self.assertEqual(mediaserver_media['speaker_email'], presentation_example['owner_mail'])
            self.assertEqual(mediaserver_media['validated'], 'yes' if presentation_example['published_status'] else 'no')
            self.assertEqual(mediaserver_media['keywords'], ','.join(presentation_example['tags']))
            self.assertEqual(mediaserver_media['slug'], 'mediasite-' + presentation_example['id'])

            self.assertIsNotNone(mediaserver_media['file_url'])
            self.assertEqual(json.loads(mediaserver_media['external_data']), presentation_example)

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
