from unittest import TestCase


class TestMetadataExtractor(TestCase):

    def __init__(self):
        self.folders_whitelist = []

    def check_whitelisting(self, folders):
        self.folders_whitelist
        for folder in folders:
            for fw in self.folders_whitelist:
                if not folder['path'].find(fw):
                    return False
        return True
