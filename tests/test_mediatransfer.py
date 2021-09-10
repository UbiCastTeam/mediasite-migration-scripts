from unittest import TestCase, SkipTest
import logging

from mediasite_migration_scripts.mediatransfer import MediaTransfer
import tests.common as common

common.set_logger(verbose=True)
logger = logging.getLogger(__name__)


def setUpModule():
    print('-> ', __name__)


class TestMediaTransfer(TestCase):

    def setUp(self):
        raise SkipTest('Work in Progress')
        super(TestMediaTransfer)
        self.config = {
            'mediaserver_url': 'https://mediatransfer.test.com',
            'mediaserver_api_key': '123-abc',
            'download_folder': "download"
        }
        self.mediasite_data = {
            'Folders': [
                {
                    'Id': '1',
                    'Name': 'GrandParent',
                    'ParentFolderId': '0',
                },
                {
                    'Id': '2',
                    'Name': 'Parent',
                    'ParentFolderId': '1',
                },
                {
                    'Id': '3',
                    'Name': 'Son',
                    'ParentFolderId': '2',
                },
                {
                    'Id': '4',
                    'Name': 'GrandSon',
                    'ParentFolderId': '3',
                },
                {
                    'Id': '5',
                    'Name': 'Orphan',
                    'ParentFolderId': '404',
                }
            ]
        }

        self.mediatransfer = MediaTransfer(self.config, self.mediasite_data)

    def tearDown(self):
        self.mediatransfer.dl_session.close()

    def test_find_folder_path(self):
        folders_list_example = self.mediasite_data
        path = ''
        for folder in folders_list_example[:4]:
            path += ('/' + folder.get('Name'))
            folder_id = folder['Id']
            path_found = self.mediatransfer.find_folder_path(folder_id, folders_list_example[:4])
            self.assertEqual(path_found, path, msg=f'Folder id = {folder_id}')

        orphan_folder_id = folders_list_example[4]['Id']
        orphan_path = self.mediatransfer.find_folder_path(orphan_folder_id, folders_list_example)
        self.assertEqual(orphan_path, '/Orphan', msg=f'Folder id = {orphan_folder_id}')

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
