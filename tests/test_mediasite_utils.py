from unittest import TestCase
import logging

import mediasite_migration_scripts.utils.common as utils
import mediasite_migration_scripts.utils.mediasite as mediasite_utils

import tests.common as tests_utils

utils.set_logger(verbose=True)
logger = logging.getLogger(__name__)


def setUpModule():
    print('-> ', __name__)


class TestMediasiteUtils(TestCase):

    def setUp(self):
        super(TestMediasiteUtils)
        self.mediasite_test_data = utils.read_json('tests/mediasite_test_data.json')

    def test_find_folder_path(self):
        folders_list_example = [
            {
                'Id': '0',
                'Name': 'Origin',
                'ParentFolderId': '',
            },
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
                'Id': '0',
                'Name': 'GrandSon',
                'ParentFolderId': '3',
            },
        ]

        path = ''
        for folder in folders_list_example:
            path += ('/' + folder.get('Name'))
            self.assertEqual(mediasite_utils.find_folder_path(folder), path)
