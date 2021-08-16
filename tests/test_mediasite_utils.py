from unittest import TestCase
import logging
import requests
from datetime import datetime

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
        self.slides_example = {
            'odata.id': 'https://anon.com/fake',
            'IsGeneratedFromVideoStream': True,
            'Id': 'ea0552005e69482d99bbd0e4d34b7ec730',
            'ParentResourceId': '0e2710f9f0bb4397a841ed64af41474b1d',
            'ContentType': 'Slides',
            'Status': 'Completed',
            'ContentMimeType': 'image/jpeg',
            'EncodingOrder': 1,
            'Length': '25',
            'FileNameWithExtension': 'slide_{0:D4}_1fd0eb59e96341caa517319a41f54a4d.jpg',
            'ContentEncodingSettingsId': '9bfd69f8cc7e48219aff3638aa43089328',
            'ContentServerId': '2127f2fa7dee41aba6cf64c777e5611829',
            'ArchiveType': 0,
            'IsTranscodeSource': False,
            'ContentRevision': 2,
            'FileLength': '2664478',
            'StreamType': 'Video1',
            'LastModified': '2013-10-04T17:09:47.57Z',
            'ContentServer': {
                'odata.metadata': 'https://anon.com/fake',
                'odata.id': 'https://anon.com/fake',
                'ContentServerId': '2127f2fa7dee41aba6cf64c777e5611829',
                'EndpointType': 'Storage',
                'UseMediasiteFileServer': True,
                'EnableFileServerSecurity': True,
                'LocalUrl': 'https://anon.com/fake',
                'Url': 'https://anon.com/fake'
            }
        }
        self.presentation_videos_streams_examples = [
            {
                'Id': 'p0',
                'Streams': [
                    {
                        'StreamType': 'Video1',
                        'StreamName': None
                    }
                ]
            },
            {
                'Id': 'p1',
                'Streams': [
                    {
                        'StreamType': 'Slide',
                        'StreamName': 'Slide with details'
                    },
                    {
                        'StreamType': 'Video3',
                        'StreamName': None
                    }
                ]
            },
            {
                'Id': 'p2',
                'Streams': [
                    {
                        'StreamType': 'Video1',
                        'StreamName': '1rst video composite'
                    },
                    {
                        'StreamType': 'Video3',
                        'StreamName': '2nd video composite'
                    }
                ]
            },
            {
                'Id': 'p3',
                'Streams': [
                    {
                        'StreamType': 'Video1',
                        'StreamName': '1rst video composite'
                    },
                    {
                        'StreamType': 'Video2',
                        'StreamName': '2nd video composite'
                    },
                    {
                        'StreamType': 'Video3',
                        'StreamName': '3rd video composite'
                    }
                ]
            }
        ]

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
        self.assertTrue(urls_ok, msg=f'missing count = {missing_count} | streams count = {streams_count}')
        self.assertEqual(missing_count, 0)
        self.assertEqual(streams_count, 2)

        urls_ok, missing_count, streams_count = mediasite_utils.check_videos_urls(videos_files_examples[1], session)
        self.assertFalse(urls_ok, msg=f'missing count = {missing_count} | streams count = {streams_count}')
        self.assertEqual(missing_count, 1)
        self.assertEqual(streams_count, 1)

    def test_get_slides_urls(self):
        slides_urls = mediasite_utils.get_slides_urls(self.slides_example)
        self.assertEqual(len(slides_urls), int(self.slides_example['Length']))
        # url pattern : {content_server_url}/{content_server_id}/Presentation/{pid}/{filename}
        self.assertEqual(slides_urls[0],
                         'https://anon.com/fake/2127f2fa7dee41aba6cf64c777e5611829/Presentation/0e2710f9f0bb4397a841ed64af41474b1d/slide_0001_1fd0eb59e96341caa517319a41f54a4d.jpg')

    def test_slides_urls_exists(self):
        self.assertFalse(mediasite_utils.slides_urls_exists(self.slides_example, session))

    def test_has_slides_details(self):
        self.assertFalse(mediasite_utils.has_slides_details(self.presentation_videos_streams_examples[0]))
        self.assertTrue(mediasite_utils.has_slides_details(self.presentation_videos_streams_examples[1]))

    def test_is_composite(self):
        for i, p in enumerate(self.presentation_videos_streams_examples):
            if i == 2:
                self.assertTrue(mediasite_utils.is_composite(p))
            else:
                self.assertFalse(mediasite_utils.is_composite(p))

    def test_parse_mediasite_data(self):
        dates_tests_set = [
            {
                'example': '2016-12-07T13:07:27.58Z',
                'expected': datetime(2016, 12, 7, 13, 7, 27, 58)
            },
            {
                'example': '2016-12-07T13:07:27',
                'expected': datetime(2016, 12, 7, 13, 7, 27)
            },
            {
                'example': '2016-12-07T13:07:27.58',
                'expected': datetime(2016, 12, 7, 13, 7, 27, 58)
            },
        ]
        for date in dates_tests_set:
            date_parsed = mediasite_utils.parse_mediasite_date(date['example'])
            self.assertEqual(date_parsed, date['expected'])

        wrong_date_parsed = mediasite_utils.parse_mediasite_date('2016-12-07T13')
        self.assertIsNone(wrong_date_parsed)
