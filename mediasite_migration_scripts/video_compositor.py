import logging
import os

logger = logging.getLogger(__name__)


class VideoCompositor():
    def __init__(self, config=dict()):
        self.config = config
        self.download_folder = '/tmp/mediasite_files/'

    def merge(self, media_folder):
        return_code = os.system(f'python3 /bin/merge.py {media_folder}')
        return return_code
