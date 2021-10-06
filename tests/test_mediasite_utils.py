from unittest import TestCase
import logging
import requests
from datetime import datetime

import mediasite_migration_scripts.utils.common as utils
import mediasite_migration_scripts.utils.mediasite as mediasite_utils

logging.getLogger('root').handlers = []
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
        self.dates_examples = [
            {
                'str': '2016-12-07T13:07:27.58Z',
                'datetime': datetime(2016, 12, 7, 13, 7, 27, 58)
            },
            {
                'str': '2016-12-07T13:07:27',
                'datetime': datetime(2016, 12, 7, 13, 7, 27)
            },
            {
                'str': '2016-12-07T13:07:27.58',
                'datetime': datetime(2016, 12, 7, 13, 7, 27, 58)
            },
        ]

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
        for date in self.dates_examples:
            date_parsed = mediasite_utils.parse_mediasite_date(date['str'])
            self.assertEqual(date_parsed, date['datetime'])

        wrong_date_parsed = mediasite_utils.parse_mediasite_date('2016-12-07T13')
        self.assertIsNone(wrong_date_parsed)

    def test_get_most_distant_date(self):
        presentations_examples = [
            {
                'Id': '0',
                'CreationDate': '2016-12-07T13:07:27.58Z',
                'RecordDate': '2016-12-07T06:07:27.58Z'
            },
            {
                'Id': '1',
                'CreationDate': '2016-12-07T13:07:27',
                'RecordDate': '2016-11-07T06:07:27.58Z'
            },
            {
                'Id': '2',
                'CreationDate': '2016-01-07T13:07:27',
                'RecordDate': '2016-11-07T06:07:27'
            }
        ]

        most_distants_dates = [mediasite_utils.get_most_distant_date(p) for p in presentations_examples]
        self.assertEqual(most_distants_dates[0], mediasite_utils.format_mediasite_date(datetime(2016, 12, 7, 6, 7, 27, 58)))
        self.assertEqual(most_distants_dates[1], mediasite_utils.format_mediasite_date(datetime(2016, 11, 7, 6, 7, 27, 58)))
        self.assertEqual(most_distants_dates[2], mediasite_utils.format_mediasite_date(datetime(2016, 1, 7, 13, 7, 27)))

    def test_parse_encoding_settings_xml(self):
        encoding_settings_example = {
            'Id': '87bc9b59ecc34e0b85b8c18d1caa383128',
            'MimeType': 'video/mp4',
            'SerializedSettings': '<EncodingSettings xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><UserMaximumDeviceClass>-1</UserMaximumDeviceClass><StreamDescriptions><EncodingStreamDescription><Number>1</Number><StreamType>Audio</StreamType><DeviceClass>1</DeviceClass><Description>AACL,64000 bps 16 bit stereo 44100 hz</Description><StreamWeight>12</StreamWeight></EncodingStreamDescription><EncodingStreamDescription><Number>2</Number><StreamType>Video</StreamType><DeviceClass>2</DeviceClass><Description>H264,700000 bps 640x360 25.000 fps</Description><StreamWeight>12</StreamWeight></EncodingStreamDescription></StreamDescriptions><Filters><EncodingSettingsFilter><FilterType>AspectRatio</FilterType><FilterValue>16x9</FilterValue></EncodingSettingsFilter><EncodingSettingsFilter><FilterType>FrameRate</FilterType><FilterValue>25</FilterValue></EncodingSettingsFilter></Filters><Settings>&lt;MediaProfile xmlns=\"http://www.SonicFoundry.com/Mediasite/Services/RecorderManagement/05/01//Data\" xmlns:i=\"http://www.w3.org/2001/XMLSchema-instance\"&gt;&lt;PresentationAspectX&gt;640&lt;/PresentationAspectX&gt;&lt;PresentationAspectY&gt;360&lt;/PresentationAspectY&gt;&lt;StreamProfiles xmlns:a=\"http://schemas.microsoft.com/2003/10/Serialization/Arrays\"&gt;&lt;a:anyType i:type=\"AudioEncoderProfile\"&gt;&lt;BitRate&gt;64000&lt;/BitRate&gt;&lt;FourCC&gt;AACL&lt;/FourCC&gt;&lt;HexEncodedCodecPrivateData&gt;1210&lt;/HexEncodedCodecPrivateData&gt;&lt;MinimumMachineClass&gt;1&lt;/MinimumMachineClass&gt;&lt;SampleRate&gt;44100&lt;/SampleRate&gt;&lt;BitsPerChannel&gt;16&lt;/BitsPerChannel&gt;&lt;BlockAlign&gt;4&lt;/BlockAlign&gt;&lt;Channels&gt;2&lt;/Channels&gt;&lt;/a:anyType&gt;&lt;a:anyType i:type=\"VideoEncoderProfile\"&gt;&lt;BitRate&gt;700000&lt;/BitRate&gt;&lt;FourCC&gt;H264&lt;/FourCC&gt;&lt;HexEncodedCodecPrivateData&gt;000000016742801E965201405FF2FFE08000800A100000030010000003032604000AAE400055737F18E30200055720002AB9BF8C70ED0913240000000168CB8D48&lt;/HexEncodedCodecPrivateData&gt;&lt;MinimumMachineClass&gt;2&lt;/MinimumMachineClass&gt;&lt;SampleRate&gt;25&lt;/SampleRate&gt;&lt;Height&gt;360&lt;/Height&gt;&lt;StreamWeight&gt;12&lt;/StreamWeight&gt;&lt;VariableRate&gt;false&lt;/VariableRate&gt;&lt;Width&gt;640&lt;/Width&gt;&lt;/a:anyType&gt;&lt;/StreamProfiles&gt;&lt;/MediaProfile&gt;</Settings></EncodingSettings>'
        }
        encoding_settings_parsed = mediasite_utils.parse_encoding_settings_xml(encoding_settings_example)
        self.assertDictEqual(encoding_settings_parsed, {
            'width': 640,
            'height': 360,
            'audio_codec': 'AAC',
            'video_codec': 'H264'
        })

        encoding_settings_example = {
            'Id': '7079dee9833a4587bd25ff6c6fb1105528',
            'MimeType': 'video/mp4',
            'SerializedSettings': '<EncodingSettings xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><UserMaximumDeviceClass>-1</UserMaximumDeviceClass><StreamDescriptions><EncodingStreamDescription><Number>1</Number><StreamType>Audio</StreamType><DeviceClass>1</DeviceClass><Description>AACL,64000 bps 16 bit stereo 44100 hz</Description><StreamWeight>0</StreamWeight></EncodingStreamDescription><EncodingStreamDescription><Number>2</Number><StreamType>Video</StreamType><DeviceClass>1</DeviceClass><Description>H264,4500000 bps 1280x960 15.000 fps</Description><StreamWeight>0</StreamWeight></EncodingStreamDescription></StreamDescriptions><Filters><EncodingSettingsFilter><FilterType>AspectRatio</FilterType><FilterValue>4x3</FilterValue></EncodingSettingsFilter><EncodingSettingsFilter><FilterType>FrameRate</FilterType><FilterValue>15</FilterValue></EncodingSettingsFilter></Filters><Settings>&lt;MediaProfile xmlns:i=\"http://www.w3.org/2001/XMLSchema-instance\" xmlns=\"http://www.SonicFoundry.com/Mediasite/Services/RecorderManagement/05/01//Data\"&gt;&lt;PresentationAspectX&gt;960&lt;/PresentationAspectX&gt;&lt;PresentationAspectY&gt;1280&lt;/PresentationAspectY&gt;&lt;StreamProfiles xmlns:d2p1=\"http://schemas.microsoft.com/2003/10/Serialization/Arrays\"&gt;&lt;d2p1:anyType i:type=\"AudioEncoderProfile\"&gt;&lt;BitRate&gt;64000&lt;/BitRate&gt;&lt;FourCC&gt;AACL&lt;/FourCC&gt;&lt;HexEncodedCodecPrivateData&gt;1210&lt;/HexEncodedCodecPrivateData&gt;&lt;MinimumMachineClass&gt;1&lt;/MinimumMachineClass&gt;&lt;SampleRate&gt;44100&lt;/SampleRate&gt;&lt;BitsPerChannel&gt;16&lt;/BitsPerChannel&gt;&lt;BlockAlign&gt;4&lt;/BlockAlign&gt;&lt;Channels&gt;2&lt;/Channels&gt;&lt;/d2p1:anyType&gt;&lt;d2p1:anyType i:type=\"VideoEncoderProfile\"&gt;&lt;BitRate&gt;4500000&lt;/BitRate&gt;&lt;FourCC&gt;H264&lt;/FourCC&gt;&lt;HexEncodedCodecPrivateData&gt;00000001674D4020965602803CDFF82000200284000003000400000300798A80008954000112A9FC638C5400044AA00008954FE31C3B4244A70000000168EA5352&lt;/HexEncodedCodecPrivateData&gt;&lt;MinimumMachineClass&gt;5&lt;/MinimumMachineClass&gt;&lt;SampleRate&gt;15&lt;/SampleRate&gt;&lt;Height&gt;960&lt;/Height&gt;&lt;VariableRate&gt;false&lt;/VariableRate&gt;&lt;Width&gt;1280&lt;/Width&gt;&lt;/d2p1:anyType&gt;&lt;/StreamProfiles&gt;&lt;/MediaProfile&gt;</Settings></EncodingSettings>'
        }
        self.assertDictEqual(mediasite_utils.parse_encoding_settings_xml(encoding_settings_example), {})

    def test_parse_timed_events_xml(self):
        timed_events_example = [
            {
                'Id': str(i),
                'Payload': f'<ChapterEntry xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"> \
                                <Number>{str(i + 1)}</Number> \
                                <Time>0</Time>  \
                                <Title>Title {str(i + 1)}</Title> \
                            </ChapterEntry>',
                'Position': (i * 1500),
                'PresentationId': 'p' + str(i)
            }
            for i in range(3)
        ]

        timed_events_parsed = mediasite_utils.parse_timed_events_xml(timed_events_example)
        for i, event_parsed in enumerate(timed_events_parsed):
            self.assertDictEqual(event_parsed, {
                'Position': timed_events_example[i]['Position'],
                'Number': str(i + 1),
                'Title': 'Title ' + str(i + 1)
            })
