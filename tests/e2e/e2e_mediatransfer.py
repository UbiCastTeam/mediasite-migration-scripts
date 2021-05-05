from unittest import TestCase
import json
import logging
import sys

from mediasite_migration_scripts.mediatransfer import MediaTransfer
from mediasite_migration_scripts.ms_client.client import MediaServerRequestError as MSReqErr
import tests.common as common


common.set_logger(verbose=True)
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

test_utils = common.MediaServerTestUtils(config)
test_channel = test_utils.create_test_channel()
test_utils.ms_client.session.close()
del test_utils.ms_client

mediasite_data = common.set_test_data()
mediasite_users = common.set_test_users()

mediatransfer = MediaTransfer(config, mediasite_data, mediasite_users, e2e_test=True, root_channel_oid=test_channel.get('oid'))
ms_client = mediatransfer.ms_client


def setUpModule():
    print('-> ', __name__, 50 * '-')


def tearDownModule():
    body = {'oid': test_channel.get('oid'), 'delete_resources': 'yes', 'delete_content': 'yes'}
    ms_client.api('channels/delete', method='post', data=body)

    for u in mediatransfer.users:
        user_channel = mediatransfer.get_user_channel(u.get('email'))
        if user_channel:
            body = {'oid': user_channel, 'delete_resources': 'yes', 'delete_content': 'yes'}
            ms_client.api('channels/delete', method='post', data=body)

        try:
            result = ms_client.api('users/delete', method='post', data={'email': u.get('email', '')}, ignore_404=True)
        except MSReqErr as e:
            result = {'success': False, 'error': e}

        if result.get('success'):
            logger.debug(f"Deleted user {u.get('username')}")
        else:
            logger.error(f"Failed to delete user {u} / Error: {result.get('error')}")

    mediatransfer.ms_client.session.close()
    ms_client.session.close()


class TestMediaTransferE2E(TestCase):
    def setUp(self):
        super().setUp()
        self.mediatransfer = mediatransfer
        self.ms_client = ms_client

        try:
            with open('tests/e2e/mediaserver_data_e2e.json') as f:
                self.mediaserver_data = json.load(f)
            self.mediatransfer.mediaserver_data = self.mediaserver_data
        except Exception as e:
            logger.debug(e)
            logger.error('Test data corrupted')
            exit(1)

    def tearDown(self):
        super().tearDown()
        try:
            with open(common.MEDIASERVER_DATA_FILE, 'w') as f:
                json.dump(self.mediaserver_data, f)
            with open(common.MEDIASERVER_USERS_FILE, 'w') as f:
                json.dump(self.mediatransfer.users, f)
        except Exception as e:
            logger.error(f'Failed to save mediaserver tests files: {e}')

        self.ms_client.session.close()

    def test_upload_medias(self):
        print('-> test_upload_medias', 20 * '-')
        medias_examples = self.mediaserver_data
        self.mediatransfer.upload_medias()

        for u in self.mediatransfer.users:
            self.check_user(u)

        for m in medias_examples:
            data = m['data']
            result = self.ms_client.api('medias/get', method='get', params={'oid': m['ref']['media_oid'], 'full': 'yes'})
            self.assertTrue(result.get("success"))
            m_uploaded = result.get('info')
            keys_to_skip = ['file_url', 'creation', 'slug', 'api_key', 'slides', 'transcode', 'detect_slides', 'video_type', 'chapters']
            for key in data.keys():
                try:
                    self.assertEqual(data[key], m_uploaded.get(key))
                except AssertionError:
                    if key == 'channel':
                        channel_title = self.mediatransfer.get_channel(oid=data['channel']).get('title')
                        self.assertEqual(channel_title, m_uploaded.get('parent_title'))
                    elif key == 'speaker_name':
                        self.assertEqual(data['speaker_name'], m_uploaded.get('speaker'))
                    elif key == 'validated' or key == 'unlisted':
                        self.assertTrue(m_uploaded.get(key)) if data[key] == 'yes' else self.assertFalse(m_uploaded.get(key))
                    elif key == 'layout' and data['layout'] == 'video':
                        self.assertEqual(m_uploaded.get('layout'), '')
                    elif key == 'channel_unlisted':
                        channel = self.ms_client.api('channels/get/', method='get', params={'oid': data['channel'], 'full': 'yes'})
                        self.assertEqual(data['channel_unlisted'], channel.get('info').get('unlisted'), msg=f'Media: {data}, Channel: {channel}')
                    elif key in keys_to_skip:
                        continue
                    else:
                        logger.error(f'[{key}] not equal')
                        raise

            self.check_slides(m)
            self.check_chapters(m)

    def check_user(self, user):
        user_created = self.ms_client.api('users/get', method='get', params={'id': user.get('id')})
        self.assertTrue(user_created.get('success'))
        for key in user.keys():
            self.assertEqual(user[key], user_created['user'][key])

    def check_slides(self, media):
        result = self.ms_client.api('annotations/slides/list/', method='get', params={'oid': media['ref'].get('media_oid')}, ignore_404=True)
        if result:
            slides_up = result.get('slides')
            slides = media['data']['slides']['urls']
            slides_details = media['data']['slides']['details']

            if slides_details:
                self.assertEqual(len(slides), len(slides_up), msg=f'slides: {len(slides)} / slides_up: {len(slides_up)}')

                for i, slide in enumerate(slides_details):
                    self.assertEqual(slide.get('TimeMilliseconds'), slides_up[i].get('time'))
                    self.assertIsNotNone(slides_up[i].get('attachment', {}).get('url'))
        else:
            logger.error('No slides found')
            raise AssertionError

    def check_chapters(self, media):
        result = self.ms_client.api('annotations/chapters/list/', method='get', params={'oid': media['ref'].get('media_oid')}, ignore_404=True)
        if result and result.get('success'):
            chapters_up = result.get('chapters')
            chapters = media['data']['chapters']
            self.assertEqual(len(chapters), len(chapters_up), msg=f'chapters: {len(chapters)} / chapters_up: {len(chapters_up)}')

            for i, chapter in enumerate(chapters):
                self.assertEqual(chapter.get('chapter_position_ms'), chapters_up[i].get('time'))
                self.assertEqual(chapter.get('chapter_title'), chapters_up[i].get('title'))

    def test_create_channels(self):
        print('-> test_create_channels', 20 * '-')

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

        channel_unlisted = self.mediatransfer.create_channels('/Baby/Love', is_unlisted=True)
        result = self.ms_client.api('channels/get', method='get', params={'oid': channel_unlisted}, ignore_404=True)
        self.assertIsNotNone(result)
        if result:
            self.assertTrue(result.get('info', {}).get('unlisted'))
        else:
            logger.error(f'Channel {channel_unlisted} not found')
