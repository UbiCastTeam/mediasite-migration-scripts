from unittest import TestCase
import json
import logging

from mediasite_migration_scripts.data_analyzer import DataAnalyzer

class TestDataExtractor(TestCase):
    def __init__(self):
        self.folders_whitelist = []
        self.analyzer = object()

    def setUp(self):
        super(TestDataExtractor)
        try:
            data = []
            with open('data.json') as f:
                data = json.load(f)
            self.analyzer = DataAnalyzer(data)
        except Exception as e:
            logging.error('No data to analyse, or data is corrupted.')
            logging.debug(e)

    def check_whitelisting(self, folders):
        self.folders_whitelist
        for folder in folders:
            for fw in self.folders_whitelist:
                if not folder['path'].find(fw):
                    return False
        return True

    def check_no_duplicate(self, folders):
        seen = {}
        for folder in self.analyzer.folders:
            for x in folder['presentations']:
                x = x['id']
                if x not in seen:
                    seen[x] = 1
                else:
                    if seen[x] > 1:
                        return False
        return True
