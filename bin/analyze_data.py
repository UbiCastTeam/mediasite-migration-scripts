#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import argparse
from argparse import RawTextHelpFormatter
import os

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
        logging.info('\nNo data to analyse, or data is corrupted.')
        run_import = input('No data to analyse.\nDo you want to run import data ? [y/N] ').lower()
        if run_import == 'y' or run_import == 'yes':
            os.system("python3 bin/import_data.py")

    analyzer = DataAnalyzer(data)

    print(f'Found {len(analyzer.folders)} folders')
    print(f'Number of presentations in folders: {len(analyzer.presentations)}')

    folders_infos = analyzer.analyse_folders()
    empty_folders = folders_infos['empty_folders']
    empty_user_folders = folders_infos['empty_user_folders']
    print(f'{len(empty_folders)} folders have no presentation inside {len(empty_user_folders)} user folders')

    videos_format_stats = analyzer.compute_videos_stats()
    with_mp4 = 0
    no_mp4 = 0
    for v_format, count in videos_format_stats.items():
        if v_format == 'video/mp4':
            with_mp4 = count
        else:
            no_mp4 += count
    print(f'{no_mp4}% of videos without mp4 vs {with_mp4}% with mp4')

    videos_layout_stats = analyzer.compute_layout_stats()
    no_slide = videos_layout_stats['mono']
    with_slides = videos_layout_stats['mono + slides']
    multiple = videos_layout_stats['multiple']
    print(f'There\'s {no_slide}% of videos with no slide, {with_slides}% with slides, and {multiple}% are compositions of multiple videos')

    mp4_analyse = analyzer.analyse_downloadable_mp4()
    downloadable_mp4 = mp4_analyse['downloadable_mp4']
    status_codes = mp4_analyse['status_codes']
    print(f'{len(downloadable_mp4)} downloadable mp4s, status codes: {status_codes}')

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
