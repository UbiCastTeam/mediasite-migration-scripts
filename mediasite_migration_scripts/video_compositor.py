#!/usr/bin/env python3
import logging
import os
import requests

logger = logging.getLogger(__name__)


class VideoCompositor:
    def __init__(self, config=dict(), dl_session=None, mediasite_auth=tuple()):
        self.config = config
        self.dl_session = dl_session
        self.mediasite_auth = mediasite_auth
        if not mediasite_auth:
            logger.error('Mediasite auth missing for video composition.')
        self.nb_folders = 0

    def download_all(self, videos, media_folder):
        for filename, url in videos.items():
            ext = url.split('.')[-1]
            if not self.download(url, media_folder / f'{filename}.{ext}'):
                return False
        return True

    def download(self, video_url, video_path=None):
        logger.debug(f'Requesting video download : {video_url}')

        if self.dl_session is None:
            self.dl_session = requests.Session()

        with self.dl_session.get(video_url, stream=True) as request:
            if video_path.is_file():
                remote_size = int(request.headers['Content-Length'])
                local_size = video_path.stat().st_size
                if remote_size == local_size:
                    logger.debug(f'Already downloaded {video_url}, skipping')
                    return True

            request.raise_for_status()
            with open(video_path, 'wb') as f:
                logger.debug(f'Downloading {video_url} to {video_path}')
                downloaded = 0
                chunk_size = 8192
                for chunk in request.iter_content(chunk_size=chunk_size):
                    total_length = int(request.headers.get('content-length'))
                    downloaded += chunk_size
                    # If you have chunk encoded response uncomment if
                    # and set chunk_size parameter to None.
                    #if chunk:
                    print(f'Downloading: {int(100 * downloaded/total_length)}%', end='\r')
                    print(' ' * 50, end='\r')
                    f.write(chunk)
            self.nb_folders += 1

        if request.ok:
            logger.debug(f'Successfuly downloaded video: {video_url}')
        else:
            logger.error(f'Failed to download video: {video_url}')

        return request.ok

    def merge(self, media_folder):
        logger.debug(f'Merging videos in folder : {media_folder}')
        output_file = media_folder / 'composite.mp4'
        layout_file = media_folder / 'mediaserver_layout.json'
        if not output_file.is_file() or output_file.stat().st_size == 0 or not layout_file.is_file():
            return_code = os.system(f'python3 bin/merge.py --width {self.config.get("composite_width", 1920)} --height {self.config.get("composite_height", 1080)} {media_folder}')
            return return_code == 0
        elif output_file.is_file() and not layout_file.is_file():
            logger.warning(f'{output_file} probably rendering, skipping')
            return False
        else:
            logger.debug(f'{output_file} and {layout_file} already found, skipping merge')
            return True
