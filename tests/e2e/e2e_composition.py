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
