import logging
import os
from pathlib import Path
import requests

logger = logging.getLogger(__name__)


class VideoCompositor():
    def __init__(self, config=dict(), dl_session=None, mediasite_auth=tuple()):
        self.config = config
        self.download_folder = Path('/tmp/mediasite_files/composition')
        self.dl_session = dl_session
        self.mediasite_auth = mediasite_auth
        if not mediasite_auth:
            logger.error('Mediasite auth missing for video composition.')

        self.nb_folders = 0

    def compose(self, videos_urls, presentation_id=str()):
        logger.debug('Composing videos files')

        video_path = Path()
        final_media_path = Path()
        dl_ok = False
        folder_name = presentation_id if presentation_id else str(self.nb_folders + 1)
        media_folder = self.download_folder / folder_name

        for url in videos_urls:
            video_path = self.download(url, media_folder)
            dl_ok = video_path.is_file()
            if not dl_ok:
                break
        if dl_ok:
            merge_ok = self.merge(media_folder)
            if merge_ok:
                final_media_path = media_folder / 'composite.mp4'
            else:
                logger.error(f'Failed to merge videos files in folder: {media_folder}')

        return final_media_path

    def download(self, video_url, media_folder):
        logger.debug(f'Downloading video : {video_url}')
        if self.dl_session is None:
            self.dl_session = requests.Session()

        video_path = Path()
        r = self.dl_session.get(video_url, auth=self.mediasite_auth)
        if r.ok:
            media_folder.mkdir(parents=True, exist_ok=True)
            video_path = media_folder / f"{video_url.split('/')[-1].split('?')[0]}"
            self.nb_folders += 1
            with open(video_path, 'wb') as f:
                f.write(r.content)
        else:
            logger.error(f'Failed to download video: {video_url}')

        return video_path

    def merge(self, media_folder):
        logger.debug(f'Merging videos in folder : {media_folder}')
        return_code = os.system(f'python3 bin/merge.py {media_folder}')
        return (return_code == 0)
