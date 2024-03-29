#!/usr/bin/env python3
import json
import argparse
import os
import sys
from pathlib import Path
import requests
import mediasite_migration_scripts.utils.common as utils
import mediasite_migration_scripts.utils.media as media


def get_video_urls(presentation):
    videos = dict()
    duration_s = 0
    slides_stream_type = presentation.get('slides', {}).get('stream_type')
    for video in presentation['videos']:
        name = video['stream_type']
        if name == slides_stream_type:
            name = 'Slides'
        for f in video['files']:
            url = f['url']
            if url.endswith('.ism'):
                continue
            has_video_track = f.get('encoding_infos', {}).get('video_codec') == 'H264' or media.has_h264_video_track(url)
            if f['size_bytes'] > 0 and f['format'] == 'video/mp4' and has_video_track:
                videos[name] = f['url']
                duration_s = max(duration_s, int(f["duration_ms"] / 1000))
                break
    return videos, duration_s


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        'presentation_ids',
        type=str,
        help='MediaSite presentation id (space separated)',
        nargs='*',
    )

    parser.add_argument(
        '--download',
        action='store_true',
        default=False,
        help='Download to folder instead of playing',
    )

    parser.add_argument(
        '--download-folder',
        type=str,
        help='Folder name for downloads',
        default='downloads/composite',
    )

    parser.add_argument(
        '--data-file',
        type=str,
        help='Path to mediasite json data',
        default='mediasite_data.json',
    )

    parser.add_argument(
        '--input-file',
        type=str,
        help='Path to file containing presentation ids (one per line)',
    )

    args = parser.parse_args()

    if not args.input_file:
        presentation_ids = args.presentation_ids
    else:
        with open(args.input_file, 'r') as f:
            d = f.read()
            presentation_ids = d.strip().split('\n')

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    presentations = list()
    print(f'Searching for {len(presentation_ids)} presentations in {args.data_file}')
    with open(args.data_file, 'r') as f:
        data = json.load(f)
        for folder in data:
            for pres in folder['presentations']:
                if pres['id'] in presentation_ids:
                    # needed to get path etc
                    pres['folder_path'] = folder['path']
                    pres['folder_id'] = folder['id']
                    pres['folder_channels'] = folder['channels']
                    presentations.append(pres)
    print(f'Found {len(presentations)} presentations')
    if presentations:
        for index, presentation in enumerate(presentations):
            pres_id = presentation['id']
            root = Path(args.download_folder) / pres_id
            print(f'Looking for video urls for {pres_id}')
            video_urls, duration_s = get_video_urls(presentation)
            if video_urls:
                if not args.download:
                    print(f'Playing {duration_s}s presentation with id {pres_id}')
                    cmd = 'gst-launch-1.0'
                    if root.is_dir():
                        print(f'Found existing folder {root}, playing from local folder')
                        for v in root.glob('*.mp4'):
                            if v.name != 'composite.mp4':
                                cmd += f' playbin uri=file://{v.resolve()}'
                    else:
                        for url in video_urls.values():
                            cmd += f' playbin uri={url}'
                    returncode = os.system(cmd)
                    if returncode != 0:
                        sys.exit()
                else:
                    print(utils.get_progress_string(index, len(presentations)) + f' Downloading {pres_id}')
                    root.mkdir(parents=True, exist_ok=True)
                    with requests.Session() as session:
                        with open(root / 'mediasite_metadata.json', 'w') as f:
                            json.dump(presentation, f, sort_keys=True, indent=4)
                        for name, url in video_urls.items():
                            local_filename = root / f'{name}.mp4'
                            with session.get(url, stream=True) as r:
                                if local_filename.is_file():
                                    remote_size = int(r.headers['Content-Length'])
                                    local_size = local_filename.stat().st_size
                                    if remote_size == local_size:
                                        print(f'Already downloaded {url}, skipping')
                                        continue
                                r.raise_for_status()
                                with open(local_filename, 'wb') as f:
                                    print(f'Downloading {url} to {local_filename}')
                                    downloaded = 0
                                    chunk_size = 8192
                                    for chunk in r.iter_content(chunk_size=chunk_size):
                                        total_length = int(r.headers.get('content-length'))
                                        downloaded += chunk_size
                                        # If you have chunk encoded response uncomment if
                                        # and set chunk_size parameter to None.
                                        #if chunk:
                                        print(f'{int(100 * downloaded/total_length)}%', end='\r')
                                        f.write(chunk)
            else:
                print(f'No video urls found for {pres_id}')
    else:
        print(f'Presentation(s) {presentation_ids} not found')
