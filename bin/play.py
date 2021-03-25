#!/usr/bin/env python3
import json
import argparse
import os
import sys


def get_video_url(presentation):
    for f in presentation['videos'][0]['files']:
        if f['size_bytes'] > 0 and f['format'] == 'video/mp4':
            return f['url']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        'presentation_ids',
        type=str,
        help='MediaSite presentation id (space separated)',
        nargs='*',
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
                    presentations.append(pres)
    print(f'Found {len(presentations)} presentations')
    if presentations:
        for presentation in presentations:
            video_url = get_video_url(presentation)
            print(f'Playing {presentation["id"]} url: {video_url}')
            returncode = os.system(f'mpv {video_url}')
            if returncode != 0:
                sys.exit()
    else:
        print(f'Presentation(s) {presentation_ids} not found')
