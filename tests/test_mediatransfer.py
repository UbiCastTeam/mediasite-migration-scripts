from unittest import TestCase
import random
import json
import logging

from mediasite_migration_scripts.mediatransfer import MediaTransfer
import tests.common as common

def setUpModule():
    print('-> ', __name__)


logger = logging.getLogger(__name__)


class FakeOptions:
    verbose = True

class TestMediaTransfer(TestCase):
    def setUp(self):
        super(TestMediaTransfer)
        self.mediasite_data = common.set_test_data()
        self.mediatransfer = MediaTransfer(self.mediasite_data, 'WARNING')
        self.ms_client = self.mediatransfer.ms_client
        self.mediaserver_data = self.mediatransfer.mediaserver_data
        common.set_logger(option=FakeOptions())

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
        while not self.mediasite_data[folder_index].get('presentations') or i < 100:
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

        self.assertGreater(len(self.mediaserver_data), 0)

        found = False
        mediaserver_media = dict()
        for media in mediaserver_data:
            if media['data']['title'] == presentation_example['title']:
                found = True
                mediaserver_media = media['data']
                break
        self.assertTrue(found)

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
            result = self.ms_client.api('medias/get', method='get', params={'title': data['title'], 'full': 'yes'})
            self.assertTrue(result.get("success"))
            m_uploaded = result.get('info')
            keys_to_skip = ['file_url', 'creation', 'slug', 'api_key']
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
                        raise
        self.mediatransfer.remove_uploaded_medias()

    def test_remove_uploaded_medias(self):
        uploaded = self.mediatransfer.upload_medias()
        removed = self.mediatransfer.remove_uploaded_medias()

        self.assertEqual(uploaded, removed)
        for media in self.mediaserver_data:
            result = self.ms_client.api('medias/get', method='get', params={'oid': media['ref']['media_oid']}, ignore_404=True)
            self.assertIsNone(result)

    def test_create_channel(self):
        # to add examples, only in path_examples
        paths_examples = ['/RATM', '/Bob Marley/Uprising', '/Pink Floyd/The Wall/Comfortably Numb', '/Tarentino/Kill Bill/Uma Turman/Katana']
        channels_examples = ''.join(paths_examples).split('/')[1:]
        channels_created_oids = list()
        for p in paths_examples:
            channels_created_oids.extend(self.mediatransfer.create_channel(p))
        self.assertEqual(len(channels_created_oids), len(channels_examples))

        ms_channels = list()
        for c in channels_examples:
            result = self.ms_client.api('channels/get', method='get', params={'title': c}, ignore_404=True)
            if result:
                ms_channels.append(result.get('info'))
            else:
                logger.error(f'Channel {c} not found')
            self.assertIsNotNone(result)

        longest_tree = paths_examples[-1].split('/')[1:]
        parent_oid = channels_created_oids[-len(longest_tree)]
        ms_tree = self.ms_client.api('channels/tree', method='get', params={'parent_oid': parent_oid})
        longest_tree.pop(0)
        for c_example in longest_tree:
            found = False
            for index, c_created in enumerate(ms_tree.get('channels')):
                if c_example == c_created.get('title'):
                    found = True
                    c_index = index
                    break
            self.assertTrue(found)
            ms_tree = ms_tree.get('channels')[c_index]

        for oid in channels_created_oids:
            channel = self.ms_client.api('channels/get', method='get', params={'oid': oid}, ignore_404=True)
            if channel:
                self.assertIn(channel.get('info').get('title'), channels_examples)
                data = {'oid': oid, 'delete_content': 'yes', 'delete_resources': 'yes'}
                logger.debug(f'Deleting channel {oid}')
                self.ms_client.api('channels/delete', method='post', data=data, ignore_404=True)

    # def test_remove_channels_created(self):
    #     paths_examples = ['/RATM', '/Bob Marley/Uprising', '/Pink Floyd/The Wall/Comfortably Numb']
    #     channels_oids = list()

    #     for p in paths_examples:
    #         channels_oids.append(self.mediatransfer.create_channel(p))
    #     self.mediatransfer.mediaserver_data = [{'data': {}, 'ref': {'channel_oid': c}} for c in channels_oids]
    #     result = self.mediatransfer.remove_channels_created()
    #     self.assertEqual(len(paths_examples), result)

    #     for media in self.mediatransfer.mediaserver_data:
    #         result = self.ms_client.api('channels/get', method='get', params={'oid': media['ref']['channel_oid']}, ignore_404=True)
    #         self.assertIsNone(result)
