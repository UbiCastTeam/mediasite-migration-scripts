from unittest import TestCase
import logging
import requests

import mediasite_migration_scripts.utils.common as utils
import mediasite_migration_scripts.utils.mediasite as mediasite_utils

import tests.common as tests_utils

utils.set_logger(verbose=True)
logger = logging.getLogger(__name__)
session = requests.session()


def setUpModule():
    print('-> ', __name__)


class TestMediasiteUtils(TestCase):

    def setUp(self):
        super(TestMediasiteUtils)

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

        path = ''
        for folder in folders_list_example[:4]:
            path += ('/' + folder.get('Name'))
            folder_id = folder['Id']
            path_found = mediasite_utils.find_folder_path(folder_id, folders_list_example[:4])
            self.assertEqual(path_found, path, msg=f'Folder id = {folder_id}')

        orphan_folder_id = folders_list_example[5]['Id']
        orphan_path = mediasite_utils.find_folder_path(orphan_folder_id, folders_list_example)
        self.assertEqual(orphan_path, '/Orphan', msg=f'Folder id = {orphan_folder_id}')

    def test_timecode_is_correct(self):
        presentations_examples = [
            {
                'Id': '0',
                'OnDemandContent': [
                    {
                        'Id': '0',
                        'Length': '2973269',
                        'FileNameWithExtension': 'v0.mp4',
                        'FileLength': '2091246582',
                        'StreamType': 'Video1',
                    }],
            },
            {
                'Id': '1',
                'OnDemandContent': [
                    {
                        'Id': '0',
                        'Length': '3100000',
                        'FileNameWithExtension': 'v1.mp4',
                        'FileLength': '1991246582',
                        'StreamType': 'Video1',
                    },
                    {
                        'Id': '1',
                        'Length': '3100000',
                        'FileNameWithExtension': 'v2.mp4',
                        'FileLength': '1991246582',
                        'StreamType': 'Video3',
                    }
                ]
            }
        ]

        test_timecode = '3000000'
        self.assertFalse(mediasite_utils.timecode_is_correct(test_timecode, presentations_examples[0]))
        self.assertTrue(mediasite_utils.timecode_is_correct(test_timecode, presentations_examples[1]))

    def test_get_video_url(self):
        video_file_examples = [
            {
                'Id': 'f0',
                'FileNameWithExtension': 'bec1b239-f06e-436a-83a8-6f196bea6e2e.mp4',
                'ContentServerId': 'ad0fce8edc61432998839c3f860b6d4429',
                'StreamType': 'Video1',
                'ContentMimeType': 'video/mp4',
                'ContentServer': {
                    'Id': 'ad0fce8edc61432998839c3f860b6d4429',
                    'Name': 'anon Name',
                    'DistributionUrl': 'https://anon.com/fake/$$NAME$$?playbackTicket=$$PBT$$&site=$$SITE$$'
                }
            },
            {
                'Id': 'f1',
                'FileNameWithExtension': 'bec1b239-f06e-436a-83a8-6f196bea6e2e.ism',
                'ContentServerId': 'ad0fce8edc61432998839c3f860b6d4429',
                'StreamType': 'Video3',
                'ContentMimeType': 'video/x-mp4-fragmented',
                'ContentServer': {
                    'Id': 'ad0fce8edc61432998839c3f860b6d4429',
                    'Name': 'anon Name',
                    'DistributionUrl': 'https://anon.com/fake/$$NAME$$?playbackTicket=$$PBT$$&site=$$SITE$$'
                }
            }
        ]

        self.assertEqual(mediasite_utils.get_video_url(video_file_examples[0]),
                         'https://anon.com/fake/bec1b239-f06e-436a-83a8-6f196bea6e2e.mp4?playbackTicket=&site=')
        self.assertEqual(mediasite_utils.get_video_url(video_file_examples[0], playback_ticket='pbt0', site='test.com'),
                         'https://anon.com/fake/bec1b239-f06e-436a-83a8-6f196bea6e2e.mp4?playbackTicket=pbt0&site=test.com')
        self.assertEqual(mediasite_utils.get_video_url(video_file_examples[1]), '')

    def test_check_videos_urls(self):
        videos_files_examples = [
            [
                {
                    'Id': 'f0',
                    'FileNameWithExtension': 'bec1b239-f06e-436a-83a8-6f196bea6e2e.mp4',
                    'ContentServerId': 'ad0fce8edc61432998839c3f860b6d4429',
                    'StreamType': 'Video1',
                    'ContentMimeType': 'video/mp4',
                    'Url': 'https://beta.ubicast.net'
                },
                {
                    'Id': 'f1',
                    'FileNameWithExtension': 'bec1b239-f06e-436a-83a8-6f196bea6e2e.mp4',
                    'ContentServerId': 'ad0fce8edc61432998839c3f860b6d4429',
                    'StreamType': 'Video3',
                    'ContentMimeType': 'video/mp4',
                    'Url': 'https://beta.ubicast.net'
                }
            ],
            [
                {
                    'Id': 'f3',
                    'FileNameWithExtension': 'bec1b239-f06e-436a-83a8-6f196bea6e2e.mp4',
                    'ContentServerId': 'ad0fce8edc61432998839c3f860b6d4429',
                    'StreamType': 'Video1',
                    'ContentMimeType': 'video/mp4',
                    'Url': 'http://hopethatneverexists123456789654123654789.com/'
                }
            ]
        ]

        urls_ok, missing_count, streams_count = mediasite_utils.check_videos_urls(videos_files_examples[0], session)
        self.assertTrue(urls_ok)
        self.assertEqual(missing_count, 0)
        self.assertEqual(streams_count, 2)

        urls_ok, missing_count, streams_count = mediasite_utils.check_videos_urls(videos_files_examples[1], session)
        self.assertFalse(urls_ok, msg=f'missing count = {missing_count} | streams count = {streams_count}')
        self.assertEqual(missing_count, 1)
        self.assertEqual(streams_count, 1)

    def test_get_slides_urls(self):
        return
