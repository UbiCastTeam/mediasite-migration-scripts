import os
import logging
from decouple import config
from unittest import TestCase
import json

from mediasite_migration_scripts.lib.mediasite_setup import MediasiteSetup


class MediaSiteTest(TestCase):
    def __init__(self):
        self.setup = object()

    def setUp(self):
        try:
            with open('config.json') as js:
                config_data = json.load(js)
            self.setup = MediasiteSetup(config_data)
        except Exception as e:
            logging.error(e)
