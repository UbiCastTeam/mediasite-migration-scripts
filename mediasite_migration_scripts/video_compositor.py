import logging
import os
from pathlib import Path
import requests

logger = logging.getLogger(__name__)


class VideoCompositor():
    def __init__(self, config=dict(), dl_session=None, mediasite_auth=tuple()):
        self.config = config
        self.download_folder = Path('/tmp/mediasite_files/')
        self.dl_session = dl_session
        self.mediasite_auth = mediasite_auth
        if not mediasite_auth:
            logger.error('Mediasite auth missing for video composition.')

    def compose(self, media_url, presentation_id):
        logger.debug(f'Composing video file  for presentation {presentation_id} : {media_url}')

        merge_ok = False
        media_folder = self.download_folder / presentation_id
        dl_ok, media_path = self.download(media_url, media_folder)

        if dl_ok:
            merge_ok = self.merge(media_folder)
            if not merge_ok:
                logger.error(f'Failed to merge video file: {media_url}')

        return merge_ok, media_path

    def download(self, media_url, media_folder):
        if self.dl_session is None:
            self.dl_session = requests.Session()

        ok = False
        media_path = Path()
        r = self.dl_session.get(media_url, auth=self.mediasite_auth)
        if r.ok:
            media_path = media_folder / f"compose_{media_url.split('/')[-1]}"

            with open(media_path, 'wb') as f:
                f.write(r.content)
            ok = r.ok

        return ok, media_path

    def merge(self, media_folder):
        return_code = os.system(f'python3 /bin/merge.py {media_folder}')
        return (return_code == 0)
