from unittest import TestCase
import logging
import sys
import json

from mediasite_migration_scripts.data_extractor import DataExtractor
import tests.common as common


common.set_logger(verbose=True)
logger = logging.getLogger(__name__)

config = {}
file = 'config.json'
try:
    with open(file) as f:
        config = json.load(f)
    config['whitelist'] = []
except Exception as e:
    logger.error('Failed to parse config file.')
    logger.debug(e)
    sys.exit(1)


def setUpModule():
    print('-> ', __name__)


class TestDataExtractorE2E(TestCase):
    def setUp(self):
        super().setUp()
        try:
            self.extractor = DataExtractor(config, max_folders=5, e2e_tests=True)
        except Exception as e:
            logger.debug(e)
            logger.error('Metadata extraction gone wrong')
            raise AssertionError

    def test_extract_mediasite_data(self):
        self.assertIsInstance(self.extractor.all_data, list)
        self.assertGreater(len(self.extractor.all_data), 0)

        folder_example = self.extractor.all_data[0]
        folder_keys = [
            'id',
            'parent_id',
            'name',
            'owner_username',
            'description',
            'catalogs',
            'path',
            'presentations'
        ]
        self.assertListEqual(folder_keys, list(folder_example.keys()))

        presentation_keys = [
            'id',
            'title',
            'creation_date',
            'presenter_display_name',
            'owner_username',
            'owner_display_name',
            'owner_mail',
            'creator',
            'other_presenters',
            'availability',
            'published_status',
            'has_slides_details',
            'description',
            'tags',
            'timed_events',
            'url',
            'videos',
            'slides'
        ]
        for folder in self.extractor.all_data:
            if len(folder.get('presentations')) > 0:
                self.assertListEqual(presentation_keys, list(folder['presentations'][0].keys()))
                break

        usernames = [user.get('username') for user in self.extractor.users]
        for i, u in enumerate(usernames):
            usernames.pop(i)
            self.assertNotIn(u, usernames)
