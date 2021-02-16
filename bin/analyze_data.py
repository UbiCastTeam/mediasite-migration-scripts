#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import argparse
from argparse import RawTextHelpFormatter
import os
import sys

from mediasite_migration_scripts.data_analyzer import DataAnalyzer
from mediasite_migration_scripts.lib.utils import MediasiteSetup

if __name__ == '__main__':
    def usage(message=''):
        return 'This script is used to extract metadata from mediasite platform'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=RawTextHelpFormatter)
        parser.add_argument('-i', '--info', action='store_true',
                            dest='info', default=False,
                            help='print more status messages to stdout.')
        parser.add_argument('-D', '--doctor', action='store_true',
                            dest='doctor', default=False,
                            help='check what presentations have not been acounted')
        parser.add_argument('-v', '--verbose', action='store_true',
                            dest='verbose', default=False,
                            help='print all status messages to stdout.')
        parser.add_argument('-d', '--dry-run', action='store_true',
                            dest='dryrun', default=False,
                            help='not really import medias.')

        return parser.parse_args()

    options = manage_opts()
    logger = MediasiteSetup.set_logger(options)

    try:
        data = []
        with open('data.json') as f:
            data = json.load(f)
    except Exception as e:
        logging.debug(e)
        logging.info('No data to analyse, or data is corrupted.')
        run_import = input('No data to analyse. Do you want to run import data ? [y/N] ').lower()
        if run_import == 'y' or run_import == 'yes':
            args = str(*sys.argv[1:])
            os.system(f'python3 bin/import_data.py {args}')
        else:
            print('--------- Aborted ---------')
            exit()

        try:
            with open('data.json') as f:
                data = json.load(f)
        except Exception as e:
            logger.debug(e)
            logger.error('Import failed')
            exit()

    analyzer = DataAnalyzer(data)

    line_sep_str = '-' * 50
    print(line_sep_str)

    print(f'Found {len(analyzer.folders)} folders')
    print(f'Number of presentations in folders: {len(analyzer.presentations)}')

    folders_infos = analyzer.analyse_folders()
    empty_folders = folders_infos['empty_folders']
    empty_user_folders = folders_infos['empty_user_folders']
    print(f'{len(empty_folders)} folders have no presentation inside {len(empty_user_folders)} user folders')

    videos_format_stats, videos_layout_stats = analyzer.analyze_videos_infos()

    with_mp4 = 0
    no_mp4 = 0
    for v_format, count in videos_format_stats.items():
        if v_format == 'video/mp4':
            with_mp4 = count
        else:
            no_mp4 += count
    print(f'{no_mp4}% of videos without mp4 vs {with_mp4}% with mp4')

    no_slide = videos_layout_stats['mono']
    with_slides = videos_layout_stats['mono + slides']
    multiple = videos_layout_stats['multiple']
    print(f'There\'s {no_slide}% of videos with no slide, {with_slides}% with slides, and {multiple}% are compositions of multiple videos')

    print(line_sep_str)

    downloadable_mp4_count = analyzer.count_downloadable_mp4s()
    downloadable_mp4 = downloadable_mp4_count['downloadable_mp4']
    status_codes = downloadable_mp4_count['status_codes']
    print(f'{len(downloadable_mp4)} downloadable mp4s, status codes: {status_codes}')

    print(line_sep_str)

    encoding_infos = analyzer.analyze_encoding_infos()
    total_duration_h = encoding_infos['total_duration_h']
    total_size_bytes = encoding_infos['total_size_bytes']
    videos_with_encoding_info = encoding_infos['videos_with_encoding_info']
    total_videos = encoding_infos['total_videos']
    video_stats = encoding_infos['video_stats']
    video_durations = encoding_infos['video_durations']

    print(f'Found {videos_with_encoding_info}/{total_videos} ({int(100 * videos_with_encoding_info / total_videos)}%) videos with encoding info', end='\n\n')

    print(f'Total duration: {int(total_duration_h)} h, total size: {int(total_size_bytes / 1000000000)} TB')
    for key, val in video_stats.items():
        print(f'{key}: {val}/{videos_with_encoding_info} TB ({int(100 * val / videos_with_encoding_info)}%)')

    print('')

    total_dur_with_info = 0
    for key, val in video_durations.items():
        total_dur_with_info += val

    print(f'Total durations with encoding infos: {total_dur_with_info} h ')
    for key, val in video_durations.items():
        print(f'{key}: {val}h / {total_dur_with_info}h ({int(100 * val / total_dur_with_info)}%)')

    if options.doctor:
        config_data = {}
        try:
            with open('config.json') as js:
                config_data = json.load(js)
        except Exception as e:
            logging.debug(e)
        mediasite = MediasiteSetup(config_data).mediasite

        print('Listing all presentations created...')
        all_presentations = mediasite.presentation.get_all_presentations()

        presentations_in_folders = analyzer.presentations
        presentations_not_in_folders = []
        for presentation_from_all in all_presentations:
            found = False
            for presentation_in_folder in presentations_in_folders:
                if presentation_from_all['id'] == presentation_in_folder['id']:
                    found = True
                    break
            if not found:
                presentations_not_in_folders.append(presentation_from_all)

        print(f'''All presentations found in Mediasite platform : {len(all_presentations)}
                Presentations not accounted in folders: {len(presentations_not_in_folders)}.''')
