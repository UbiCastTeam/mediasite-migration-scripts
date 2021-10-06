from unittest import TestCase
import logging
import json

import mediasite_migration_scripts.utils.common as utils
import tests.common as test_utils

logging.getLogger('root').handlers = []
utils.set_logger(verbose=True)
logger = logging.getLogger(__name__)

config = utils.read_json('config-test.json')
mediatransfer, ms_client = test_utils.prepare_test_data_and_clients(config)


def setUpModule():
    print('-> ', __name__, 50 * '-')


def tearDownModule():
    mediatransfer.ms_client.session.close()
    ms_client.session.close()


class TestMediaTransferE2E(TestCase):
    def setUp(self):
        super().setUp()
        self.mediatransfer = mediatransfer
        self.ms_client = ms_client

    def tearDown(self):
        super().tearDown()
        self.ms_client.session.close()

    def test_upload_medias(self):
        print('-> test_upload_medias', 20 * '-')
        self.mediatransfer.upload_medias()
        medias_examples = self.mediatransfer.mediaserver_data

        keys_to_skip_checking_for_equality = [
            'channel_title',
            'channel_unlisted',
            'transcode',
            'detect_slides',
            'slides',
            'chapters',
            'video_type',
            'file_url',
            'composites_videos_urls',
            'speaker_id',
            'speaker_name',
            'channel',
            'priority',
            'validated',
            'layout_preset',
            'thumb'
        ]
        wmv_ok = False
        audio_only_ok = False
        for media_origin in medias_examples:
            media_oid = media_origin['ref']['media_oid']
            result = self.ms_client.api('medias/get', method='get', params={'oid': media_oid, 'full': 'yes'})
            self.assertTrue(result.get('success'))

            media_result = result.get('info')
            for key, val in media_origin['data'].items():
                res = media_result.get(key)
                if key not in keys_to_skip_checking_for_equality:
                    self.maxDiff = None
                    self.assertEqual(val, res, msg=f'on key [{key}]')
                elif key == 'validated':
                    self.assertEqual(val == 'yes', res, msg=f'on key [{key}]')
                elif key == 'layout_preset':
                    layout_origin_dict = json.loads(val)
                    layout_res_dict = json.loads(res)
                    self.assertEqual(layout_origin_dict['composition_area'], layout_res_dict['composition_area'])
                    for i, layer_res in enumerate(layout_res_dict['composition_data'][0]['layers']):
                        del layer_res['z']
                        self.assertEqual(layout_origin_dict['layers'][i], layer_res)

            if media_origin.get('chapters'):
                self._check_chapters(media_origin)
            self._check_slides(media_origin)

            self.assertLessEqual(len(media_result.get('keywords', '')), 254)

            media_title = media_result['title']
            channel_title = media_result['parent_title']
            if media_title == 'Media with channel with 2 catalogs':
                self.assertEqual(channel_title, 'Recent Catalog')
            elif media_title == 'Media with parent parent folder without catalog':
                channel = self.ms_client.api(
                    'channels/get', method='get', params={'title': channel_title})
                self.assertTrue(channel['info']['unlisted'])
            elif media_title == 'Media in registered user channel':
                self.assertEqual(channel_title, 'test-user-from-mediasite')
                self.assertEqual(media_result['path'][0]['title'], 'Chaînes personnelles')
            elif media_title == 'Media in unknown user channel':
                channel = self.ms_client.api('channels/get', method='get', params={'title': channel_title})
                self.assertEqual(channel['info']['parent_title'], mediatransfer.config['mediaserver_unknown_users_channel'])
            elif media_title == 'Media with wmv ok':
                res = self.ms_client.api('medias/resources-list', method='get', params={'oid': media_oid})
                if res.get('success'):
                    medias_resources = res['resources']
                    for r in medias_resources:
                        self.assertIn('.wmv', r.get('file'))
                    wmv_ok = True
            elif media_title == 'Media with audio only':
                audio_only_ok = True
                self.assertNotEqual(media_result['thumb'], 'https://beta.ubicast.net/static/mediaserver/images/video.png')

        self.assertTrue(wmv_ok)
        self.assertTrue(audio_only_ok)

    def _check_slides(self, media_origin):
        result = self.ms_client.api('annotations/slides/list/', method='get', params={'oid': media_origin['ref'].get('media_oid')}, ignore_404=True)
        if result:
            slides_up = result.get('slides')
            slides = media_origin.get('slides')

            if slides:
                slides_count = slides.get('Length')
                self.assertEqual(slides_count, len(slides_up), msg=f'slides: {slides_count} / slides_up: {len(slides_up)}')
                for i, slide in enumerate(slides['SlideDetails']):
                    self.assertEqual(slide.get('TimeMilliseconds'), slides_up[i].get('time'))
                    self.assertIsNotNone(slides_up[i].get('attachment', {}).get('url'))
        else:
            logger.error('No slides found')
            raise AssertionError

    def _check_chapters(self, presentation, media):
        result = self.ms_client.api('annotations/chapters/list/', method='get', params={'oid': media['ref'].get('media_oid')}, ignore_404=True)
        if result and result.get('success'):
            chapters_up = result.get('chapters')
            timed_events_count = len(presentation['TimedEvents'])
            self.assertEqual(timed_events_count, len(chapters_up), msg=f'timed_events: {timed_events_count} / chapters_up: {len(chapters_up)}')

            chapters = media['data']['chapters']
            for i, chapter in enumerate(chapters):
                self.assertEqual(chapter.get('Position'),
                                 chapters_up[i].get('time'))
                self.assertEqual(chapter.get('Title'),
                                 chapters_up[i].get('title'))
        else:
            logger.error('Failed to migrate chapters')
            raise AssertionError
