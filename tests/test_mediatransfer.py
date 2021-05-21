from unittest import TestCase
import json
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
        self.mediasite_data = common.set_test_data()
        self.mediatransfer = MediaTransfer(mediasite_data=self.mediasite_data, unit_test=True)
        self.mediaserver_data = self.mediatransfer.mediaserver_data

    def tearDown(self):
        try:
            with open(common.MEDIASERVER_DATA_FILE, 'w') as f:
                json.dump(self.mediaserver_data, f)
        except Exception as e:
            logger.error(f'Failed to save mediaserver data file: {e}')

    def test_to_mediaserver_keys(self):
        mediaserver_data = self.mediatransfer.to_mediaserver_keys()
        try:
            with open('tests/mediaserver_data_test.json', 'w') as f:
                json.dump(mediaserver_data, f)
        except Exception as e:
            logger.error(e)

        len_presentations = 0
        for folder in self.mediasite_data:
            for index, presentation in enumerate(folder.get('presentations')):
                len_presentations += 1
                for media in self.mediaserver_data:
                    data = media.get('data', {})
                    if data['slug'] == 'mediasite-' + presentation['id']:
                        has_catalog = len(folder.get('catalogs', [])) > 0
                        channel_name = folder['catalogs'][0].get('name') if has_catalog else folder.get('name')
                        self.assertEqual(data['channel_title'], channel_name)
                        self.assertIn('channel_unlisted', data)
                        self.assertNotEqual(data['channel_unlisted'], has_catalog)
                        if has_catalog:
                            channel_path_splitted = folder['path'].split('/')
                            channel_path_splitted[-1] = channel_name
                            path = '/'.join(channel_path_splitted)
                        else:
                            path = folder['path']
                        self.assertEqual(media['ref']['channel_path'], path)

                        self.assertEqual(data['title'], presentation['title'])
                        self.assertEqual(data['creation'], presentation['creation_date'])
                        self.assertEqual(data['speaker_id'], presentation['owner_username'])
                        self.assertEqual(data['speaker_name'], presentation['owner_display_name'])
                        self.assertEqual(data['speaker_name'], presentation['owner_display_name'])
                        self.assertEqual(data['speaker_email'], presentation['owner_mail'])
                        self.assertEqual(data['validated'], 'yes' if presentation['published_status'] else 'no')
                        self.assertEqual(data['keywords'], ','.join(presentation['tags']))
                        self.assertEqual(data['transcode'], 'yes' if data['video_type'] == 'audio_only' else 'no',
                                         msg='Audio only medias must be transcoded')
                        self.assertEqual(data['detect_slides'], 'yes' if data['video_type'] == 'computer_slides' or data['video_type'] == 'composite_slides' else 'no',
                                         msg='Slide detection must be on if the media is "computer_slides" or "composites_slides" type')

                        if data['video_type'] == 'video_slides':
                            self.assertEqual(data['layout'], 'webinar')
                        elif data['video_type'] in ['composite_video', 'composite_slides']:
                            self.assertEqual(data['layout'], 'composition')
                        else:
                            self.assertEqual(data['layout'], 'video')

                        self.assertEqual(data['chapters'], presentation['timed_events'])

                        self.assertTrue(data['file_url'])
                        if data['file_url'] == 'local_files_to_compose':
                            self.assertTrue(data['videos_composites_urls'])

        self.assertEqual(len_presentations, len(self.mediaserver_data))
