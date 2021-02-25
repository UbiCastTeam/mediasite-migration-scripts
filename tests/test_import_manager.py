from unittest import TestCase
import json
import logging

from mediasite_migration_scripts.import_manager import MediaServerImportManager
import tests.common as common

class TestImportManager(TestCase):

    def setUp(self):
        super(TestImportManager)
        self.data = common.make_test_data()
        self.ms_import = MediaServerImportManager(self.data)

    def test_set_presentations(self):
        presentations_in_data = self.data[0]['presentations']
        presentations_example = self.ms_import._set_presentations()
        for p in presentations_in_data:
            self.assertIn(p, presentations_example)
