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