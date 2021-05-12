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
            self.extractor = DataExtractor(config, max_folders=10, e2e_tests=True)
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
        catalogs_example = folder_example['catalogs']
        if catalogs_example:
            folder_keys.append('linked_catalog_id')

        for key in folder_keys:
            self.assertIn(key, folder_example.keys())

        catalogs_keys = [
            'id',
            'name',
            'description',
            'url',
            'owner_username',
            'creation_date'
        ]
        found_linked_catalog = False
        for c_example in catalogs_example:
            if folder_example.get('linked_catalog_id') == c_example.get('id'):
                found_linked_catalog = True
                self.assertEqual(folder_example.get('name'), c_example.get('name'))
            for key in catalogs_keys:
                self.assertIn(key, c_example.keys())
        self.assertTrue(found_linked_catalog)

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
            'total_views',
            'last_viewed',
            'url',
            'videos',
            'slides'
        ]
        for folder in self.extractor.all_data:
            if len(folder.get('presentations')) > 0:
                self.assertListEqual(presentation_keys, list(folder['presentations'][0].keys()))
                break

        self.assertIsInstance(self.extractor.users, list)

        usernames = [user.get('username') for user in self.extractor.users]
        for i, u in enumerate(usernames):
            self.assertIn(u, usernames)
            usernames.pop(i)
            self.assertNotIn(u, usernames)
