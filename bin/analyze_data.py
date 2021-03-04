#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import argparse
from argparse import RawTextHelpFormatter
import os
import sys

from mediasite_migration_scripts.data_analyzer import DataAnalyzer
from mediasite_migration_scripts.lib.mediasite_setup import MediasiteSetup
from mediasite_migration_scripts.lib import utils

if __name__ == '__main__':
    def usage(message=''):
        return 'This script is used to extract metadata from mediasite platform'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=RawTextHelpFormatter)
        parser.add_argument(
            '-i',
            '--info',
            action='store_true',
            default=False,
            help='print more status messages to stdout.',
        )
        parser.add_argument(
            '-D',
            '--doctor',
            action='store_true',
            default=False,
            help='check what presentations have not been acounted',
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            default=False,
            help='print all status messages to stdout.',
        )
        parser.add_argument(
            '-c',
            '--check-resources',
            action='store_true',
            default=False,
            help='check if every video resource can be downloaded or not (slow).',
        )
        parser.add_argument(
            '--dump',
            action='store_true',
            default=False,
            help='store reports and presentation ids into separate files (e.g. presentations_composite_videos.txt)'
        )
        parser.add_argument(
            '-d',
            '--dry-run',
            action='store_true',
            dest='dryrun',
            default=False,
            help='not really import medias.'
        )

        return parser.parse_args()

    options = manage_opts()
    logger = utils.set_logger(options=options)

    file = 'mediasite_data_debug.json' if options.dryrun else 'mediasite_data.json'
    try:
        data = []
        with open(file) as f:
            data = json.load(f)
    except Exception as e:
        logging.debug(e)
        logging.info('No data to analyse, or data is corrupted.')
        run_import = input('No data to analyse. Do you want to run import data ? [y/N] ').lower()
        if run_import == 'y' or run_import == 'yes':
            args = ' '.join(sys.argv[1:])
            os.system(f'python3 bin/import_data.py {args}')
        else:
            print('--------- Aborted ---------')
            exit()

        try:
            with open(file) as f:
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
    print(f'Found {len(analyzer.catalogs)} catalogs linked to folders')

    folder_in_catalogs = list()
    for folder in analyzer.folders:
        if len(folder['catalogs']) > 0:
            folder_in_catalogs.append(folder)

    print(f'Number of folders linked to catalogs: {len(folder_in_catalogs)}')

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

    if options.check_resources:
        downloadable_mp4_count = analyzer.count_downloadable_mp4s()
        downloadable_mp4 = downloadable_mp4_count['downloadable_mp4']
        status_codes = downloadable_mp4_count['status_codes']
        print(f'{len(downloadable_mp4)} downloadable mp4s, status codes: {status_codes}')

        print(line_sep_str)

    encoding_infos = analyzer.analyze_encoding_infos(options.dump)
    video_stats = encoding_infos['video_stats']

    text = 'Format\tFormat pixels per frame\tDuration_hours\tCount\tSize_gbytes\tCreated this year\n'
    for key, val in encoding_infos['video_stats'].items():
        stats = '{pixels}\t{duration_hours}\t{count}\t{size_gbytes}\t{less_than_one_year_old}'.format(**val)
        text += f'{key}\t{stats.replace(".", ",")}\n'

    print()
    print(text)
    if options.dump:
        with open('presentations_format_list.txt', 'w') as f:
            f.write(text)

    def get_percent(x, total):
        return int(100 * x / total)

    print()
    print('{total_importable} / {total_video_count} importable videos ({total_duration_h} hours, {total_size_tb} TB)'.format(**encoding_infos))
    print()
    print(encoding_infos['video_types_stats'])
    print()

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
