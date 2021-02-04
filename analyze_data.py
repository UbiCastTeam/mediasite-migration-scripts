#!/usr/bin/env python3
import json
import requests
import sys

input_file = sys.argv[1]

with open(input_file, 'r') as f:
    folders = json.load(f)

print(f'Found {len(folders)} folders')

empty_folders = list()
empty_user_folders = list()
no_mp4 = list()
with_mp4 = list()
more_than_one_presentation = list()
exactly_one_presentation = list()
mp4_urls = list()

for folder in folders:
    if folder['presentations']:
        videos = folder['presentations'][0]['videos']
        if len(folder['presentations']) > 1:
            more_than_one_presentation.append(folder)
        else:
            exactly_one_presentation.append(folder)
        has_mp4 = False
        for video in videos:
            files = video['files']
            if not has_mp4:
                for f in files:
                    video_format = f['format']
                    if video_format == 'video/mp4':
                        has_mp4 = True
                        mp4_urls.append(f['url'])
                        break
        if not has_mp4:
            no_mp4.append(folder)
        else:
            with_mp4.append(folder)
    else:
        if 'Mediasite Users' in folder['path']:
            empty_user_folders.append(folder)
        empty_folders.append(folder)

print(f'{len(empty_folders)} folders have no presentation inside {len(empty_user_folders)} user folders)')
print(f'{len(no_mp4)} videos without mp4 vs {len(with_mp4)} with mp4')

