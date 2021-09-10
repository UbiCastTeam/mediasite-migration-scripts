from pathlib import Path
from unittest import TestCase
import logging
import json

from mediasite_migration_scripts.mediatransfer import MediaTransfer
import mediasite_migration_scripts.utils.common as utils
import mediasite_migration_scripts.utils.mediasite as mediasite_utils
import mediasite_migration_scripts.utils.mediaserver as mediaserver_utils

import tests.common as test_utils

logging.getLogger('root').handlers = []
utils.set_logger(verbose=True)
logger = logging.getLogger(__name__)

try:
    config = utils.read_json('config-test.json')
    ms_utils = mediaserver_utils.MediaServerUtils(config)
    ms_client = ms_utils.ms_client

    media_sample_infos = {
        'oid': 'v12619b7260509beg5up',
        'url': 'https://beta.ubicast.net/resources/r12619b72604fpsvrzrflm70x1ad6z/media_720_0t4Q5Qjsx2.mp4'
    }
    media_sample = ms_client.api(
        'download',
        method='get',
        params={'oid': media_sample_infos['oid'], 'url': media_sample_infos['url'], 'redirect': 'no'}
    )

    if not media_sample.get('success'):
        logger.error('Failed to get urls for medias samples from Mediaserver')

    media_url_without_base = media_sample.get('url').replace(config.get('mediaserver_url'), '')
    mediasite_data = utils.read_json('tests/anon_data.json')
    for folder in mediasite_data['Folders']:
        for presentation in folder['Presentations']:
            for video in presentation['OnDemandContent']:
                video['FileNameWithExtension'] = media_url_without_base

    mediatransfer = MediaTransfer(config, mediasite_data)

    test_channel_oid = ms_utils.create_test_channel()
    mediatransfer.root_channel = mediatransfer.get_channel(test_channel_oid)
    for media in mediatransfer.mediaserver_data:
        m_data = media.get('data', {})
        if m_data.get('video_type') == "composite_video":
            m_data['composites_videos_urls'] = {'Video1': media_sample.get('url'), 'Video3': media_sample.get('url')}
        else:
            m_data['file_url'] = media_sample

    mediatransfer.slides_folder = Path('tests/samples/slides')
    mediatransfer.mediaserver_data[0]['data']['slides'] = test_utils.generate_slides_details()

except Exception as e:
    logger.debug(e)
    logger.error('Failed to prepare test data')
    exit(1)


def setUpModule():
    print('-> ', __name__, 50 * '-')


def tearDownModule():
    body = {'oid': test_channel_oid, 'delete_resources': 'yes', 'delete_content': 'yes'}
    ms_client.api('channels/delete', method='post', data=body)

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
        medias_examples = self.mediatransfer.mediaserver_data
        self.mediatransfer.upload_medias()

        for media in medias_examples:
            result = self.ms_client.api('medias/get', method='get', params={'oid': media['ref']['media_oid'], 'full': 'yes'})
            self.assertTrue(result.get('success'))
            media_info = result.get('info')
            media_origin_pid = json.loads(media['data']['external_data'])['Id']
            presentation_origin = mediatransfer.get_presentation_by_id(media_origin_pid)

            presentation_key_mapping = {
                'Id': 'external_ref',
                'Title': 'title',
                'Owner': 'speaker_id',
            }
            for mst_key, ms_key in presentation_key_mapping.items():
                self.assertEqual(presentation_origin[mst_key], media_info[ms_key], msg=f'{mst_key} -> {ms_key}')

            creation_date = mediasite_utils.get_most_distant_date(presentation_origin)
            mst_date = mediasite_utils.parse_mediasite_date(creation_date)
            ms_date = mediaserver_utils.parse_mediaserver_date(media_info['creation'])
            self.assertEqual(mst_date, ms_date)

            pid = presentation_origin["Id"]
            expected_results = {
                'slug': f'mediasite-{pid}',
                'keywords': ','.join(presentation_origin['TagList']),
                'parent_title': mediatransfer.get_presentation_parent_folder(pid)['Name']
            }
            for key, expected in expected_results.items():
                self.assertEqual(media_info[key], expected)

            if presentation_origin.get('TimedEvents'):
                self._check_chapters(presentation_origin, media)
            self._check_slides(presentation_origin, media)

    def _check_slides(self, presentation, media):
        result = self.ms_client.api('annotations/slides/list/', method='get', params={'oid': media['ref'].get('media_oid')}, ignore_404=True)
        if result:
            slides_up = result.get('slides')
            slides = presentation.get('SlideDetailsContent')

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
                self.assertEqual(chapter.get('Position'), chapters_up[i].get('time'))
                self.assertEqual(chapter.get('Title'), chapters_up[i].get('title'))
        else:
            logger.error('Failed to migrate chapters')
            raise AssertionError()
