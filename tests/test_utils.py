from unittest import TestCase
import logging
from pymediainfo import Track
import requests
from pathlib import Path
import os


import mediasite_migration_scripts.utils.common as utils
import mediasite_migration_scripts.utils.media as media
import mediasite_migration_scripts.utils.http as http
from mediasite_migration_scripts.utils.data_filter import DataFilter
import mediasite_migration_scripts.utils.order as order

logging.getLogger('root').handlers = []
utils.set_logger(verbose=True)
logger = logging.getLogger(__name__)
session = requests.session()


def setUpModule():
    print('-> ', __name__)


class TestUtils(TestCase):

    def setUp(self):
        super(TestUtils)
        sample_dir = 'tests/samples'
        self.media_with_sound = f'{sample_dir}/MEDIA_WITHSOUND.mp4'
        self.media_wmv_with_no_sound = f'{sample_dir}/MEDIA_WMV_NOSOUND.wmv'
        self.data = utils.read_json('tests/anon_data.json')
        self.filtered_data = utils.read_json('tests/anon_data_filtered.json')

    def test_is_folder_to_add(self):
        config_example = {'whitelist': ['/folder/example', '/another_folder']}

        whitelisted_paths_examples = ['/folder/example/', '/folder/example', '/another_folder', 'parent_folder/another_folder']
        for path_example in whitelisted_paths_examples:
            self.assertTrue(utils.is_folder_to_add(path_example, config_example))

        skipped_paths_examples = ['/folder', '/skipped_folder', '/skipped_folder/example', '/', '']
        for path_example in skipped_paths_examples:
            self.assertFalse(utils.is_folder_to_add(path_example, config_example), msg=f'path example = {path_example}')

    def test_read_json(self):
        json_path_example = 'tests/samples/test.json'
        json_read = utils.read_json(json_path_example)
        self.assertIsNotNone(json_read)
        self.assertTrue(json_read.get('test'))

        wrong_json_path_example = 'wrong_folder/wrong_path.json'
        json_read = utils.read_json(wrong_json_path_example)
        self.assertIsNone(json_read)

    def test_write_json(self):
        json_path_example = Path('tests/json_folder/write_test.json')

        data = {'write_json_test': True}
        utils.write_json(data, json_path_example)
        self.assertTrue(json_path_example.is_file())

        os.remove(json_path_example)
        parent_dir = json_path_example.parent
        parent_dir.rmdir()

    def test_write_csv(self):
        filename_example = Path('test_write.csv')
        fields_example = [f'Field {i}' for i in range(3)]
        rows_example = [{fields: i for i, fields in enumerate(fields_example)}
                        for i in range(3)]

        utils.write_csv(filename_example, fields_example, rows_example)
        self.assertTrue(filename_example.is_file())
        os.remove(filename_example)

    def test_store_object_data_in_json(self):
        class ObjExample:
            def __init__(self):
                self.attr1 = 'loulou'
                self.attr2 = ['loulou', 'lala']
                self.attr3 = {'a': 1, 'b': 3}

        obj = ObjExample()
        attributes = ['attr1', 'attr2', 'attr3']
        for attr in attributes:
            path_prefix = 'tests/test_example'
            utils.store_object_data_in_json(obj, attr, path_prefix)
            path = Path(path_prefix + '_' + attr + '.json')
            self.assertTrue(path.is_file(), msg=f'path = {path}')
            os.remove(path)

    def test_to_mediaserver_conf(self):
        mediasite_conf_example = {
            'mediasite_api_url': 'https://anon.com',
            'mediasite_api_key': '1234-mst-key',
            'mediasite_api_user': 'mediasite_user',
            'mediasite_api_password': '0',
            'mediaserver_api_key': '1234-ms-key',
            'mediaserver_url': 'https://anon.ubicast.net/',
        }

        mediaserver_conf = utils.to_mediaserver_conf(mediasite_conf_example)
        self.assertEqual(mediaserver_conf['API_KEY'], mediasite_conf_example['mediaserver_api_key'])
        self.assertEqual(mediaserver_conf['SERVER_URL'], mediasite_conf_example['mediaserver_url'])

    def test_get_timecode_from_sec(self):
        times_sec_examples = [
            {
                'example': 0,
                'expected': '0:00:00',
            },
            {
                'example': 1625,
                'expected': '0:27:05',
            },
            {
                'example': 83569,
                'expected': '23:12:49',
            },
            {
                'example': -3000,
                'expected': '0:00:00',
            },
        ]
        for t in times_sec_examples:
            self.assertEqual(utils.get_timecode_from_sec(t['example']), t['expected'])

    def test_get_tracks(self):
        tracks_example = media.get_tracks(self.media_with_sound)
        self.assertIsNotNone(tracks_example)
        for track in tracks_example:
            self.assertTrue(isinstance(track, Track))

    def test_has_h264_video_track(self):
        self.assertTrue(media.has_h264_video_track(self.media_with_sound))
        self.assertFalse(media.has_h264_video_track(self.media_wmv_with_no_sound))

    def test_get_duration_h(self):
        videos_examples = [
            {
                'example': [
                    {
                        'Id': 'v0',
                        'Length': '2973269',
                    },
                ],
                'expected': 0.83
            },
            {
                'example': [
                    {
                        'Id': 'v1',
                        'Length': '5616000',
                    },
                    {
                        'Id': 'v1b',
                        'Length': '5616000',
                    }
                ],
                'expected': 1.56
            },
            {
                'example': [
                    {
                        'Id': 'v2',
                        'Length': '0',
                    },
                ],
                'expected': 0
            },
            {
                'example': [
                    {
                        'Id': 'v3',
                        'Length': '-500',
                    },
                ],
                'expected': 0
            }
        ]

        for v in videos_examples:
            self.assertEqual(media.get_duration_h(v['example']), v['expected'])

    def test_parse_encoding_infos_with_mediainfo(self):
        encoding_infos_example = media.parse_encoding_infos_with_mediainfo(self.media_with_sound)
        self.assertDictEqual(encoding_infos_example, {
            'video_codec': 'H264',
            'audio_codec': 'AAC',
            'height': 720,
            'width': 1280
        })

        encoding_infos_wmv_with_no_sound_example = media.parse_encoding_infos_with_mediainfo(self.media_wmv_with_no_sound)
        self.assertDictEqual(encoding_infos_wmv_with_no_sound_example, {
            'video_codec': 'MPEG-4 Visual',
            'height': 360,
            'width': 640
        })

    def test_url_exists(self):
        self.assertTrue(http.url_exists('https://beta.ubicast.net', session))
        self.assertFalse(http.url_exists('wrong-url.com_fr.you', session))

    def test_order_and_filter_videos(self):
        folders = self.data['Folders']
        ordered_videos = list()
        for f in folders:
            for p in f['Presentations']:
                video = order.order_and_filter_videos(p)
                if video:
                    ordered_videos.append(video)
        expected_ordered_videos = utils.read_json('tests/anon_ordered_videos.json')
        self.assertListEqual(ordered_videos, expected_ordered_videos)

    def test_filter_data(self):
        self.skipTest(reason='Method not used')
        data = self.data
        filters = {
            'Folders': [
                'Id',
                'Name',
                {'Catalogs': ['Id', 'Name']},
                {
                    'Presentations': [
                        'Id',
                        'Title',
                        {
                            'OnDemandContent': [
                                'FileNameWithExtension',
                                'StreamType',
                                'ContentMimeType',
                                {'ContentServer': ['Id', 'DistributionUrl']}
                            ]
                        }
                    ]
                }
            ]
        }
        data_filter = DataFilter(filters)
        filtered_data = data_filter.filter_data(data)
        expected_filtered_data = self.filtered_data
        self.assertDictEqual(filtered_data, expected_filtered_data)

        filtered_folders = filtered_data.get('Folders')
        self.assertIsNotNone(filtered_folders)
        folders = data['Folders']

        for f_index, f_filtered in enumerate(filtered_folders):
            f_origin = folders[f_index]
            self.assertEqual(f_filtered.get('Id'), f_origin['Id'])

            catalogs = f_filtered.get('Catalogs')
            self.assertIsNotNone(catalogs)
            for c_index, c_filtered in enumerate(catalogs):
                self.assertEqual(c_filtered.get('Id'), f_origin['Catalogs'][c_index]['Id'])

            presentations = f_filtered.get('Presentations')
            self.assertIsNotNone(presentations)
            for p_index, p_filtered in enumerate(presentations):
                p_origin = f_origin['Presentations'][p_index]
                self.assertEqual(p_filtered.get('Id'), p_origin['Id'])

                videos = p_filtered.get('OnDemandContent')
                self.assertIsNotNone(videos)
                for v_index, v_filtered in enumerate(videos):
                    v_origin = p_origin['OnDemandContent'][v_index]
                    self.assertEqual(v_filtered.get('FileNameWithExtension'), v_origin['FileNameWithExtension'])
                    self.assertEqual(v_filtered.get('ContentServer', {}).get('Id'), v_origin['ContentServer']['Id'])
