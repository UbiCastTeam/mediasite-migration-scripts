#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import argparse
from argparse import RawTextHelpFormatter
import os
import sys

from mediasite_migration_scripts.data_analyzer import DataAnalyzer
import mediasite_migration_scripts.utils.common as utils

if __name__ == '__main__':
    def usage(message=''):
        return 'This script is used to extract metadata from mediasite platform'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=RawTextHelpFormatter)
        parser.add_argument(
            '-q',
            '--quiet',
            dest='quiet', default=False,
            help='Print less information to stdout.'
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            default=False,
            help='Print all information to stdout.',
        )
        parser.add_argument(
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
            '--mediasite-file',
            action='store_true',
            default='mediasite_data.json',
            help='add custom mediasite data file.'
        )
        parser.add_argument(
            '--config-file',
            action='store_true',
            default='config.json',
            help='Json config file.'
        )
        return parser.parse_args()

    options = manage_opts()
    logger = utils.set_logger(options=options)

    mediasite_data_file = options.mediasite_file

    should_run_import = False
    if not os.path.isfile(mediasite_data_file):
        logging.info(f'Data file {options.mediasite_file} not found')
        should_run_import = True
    else:
        try:
            with open(mediasite_data_file) as f:
                data = json.load(f)
        except Exception as e:
            logging.info('Data file {options.mediasite_file} seems corrupted')
            logging.debug(e)
            should_run_import = True
    if should_run_import:
        run_import = input('No data to analyze. Do you want to run import data ? [y/N] ').lower()
        if run_import == 'y' or run_import == 'yes':
            args = ' '.join(sys.argv[1:])
            returncode = os.system(f'python3 bin/collect.py {args}')
            if returncode != 0:
                logging.error('Failed to import data')
                sys.exit(1)
            else:
                try:
                    with open(mediasite_data_file) as f:
                        data = json.load(f)
                except Exception as e:
                    logging.info(f'Data file {options.mediasite_file} seems corrupted')
                    logging.debug(e)
                    sys.exit(1)
        else:
            logger.info('--------- Aborted ---------')
            sys.exit(1)

    config_file = options.config_file
    config_data = {}
    try:
        if os.path.isfile(config_file):
            logging.info(f'Loading config file {config_file}')
            with open(config_file) as js:
                config_data = json.load(js)
    except Exception as e:
        logging.error(e)

    analyzer = DataAnalyzer(data, config_data)

    folder_in_catalogs = list()
    for folder in analyzer.folders:
        if len(folder['catalogs']) > 0:
            folder_in_catalogs.append(folder)

    if options.check_resources:
        downloadable_mp4_count = analyzer.count_downloadable_mp4s()
        downloadable_mp4 = downloadable_mp4_count['downloadable_mp4']
        status_codes = downloadable_mp4_count['status_codes']
        print(f'Found {len(downloadable_mp4)} downloadable mp4s, status codes: {status_codes}')

    logger.info('Computing stats')
    videos_format_stats, videos_layout_stats = analyzer.analyze_videos_infos()
    encoding_infos = analyzer.analyze_encoding_infos(options.dump)

    logger.info('Processing finished, displaying results')

    text = 'Format\tFormat pixels per frame\tDuration_hours\tCount\tSize_gbytes\tCreated this year\n'
    for key, val in encoding_infos['video_stats'].items():
        stats = '{pixels}\t{duration_hours}\t{count}\t{size_gbytes}\t{less_than_one_year_old}'.format(**val)
        # for google docs number formatting
        text += f'{key}\t{stats.replace(".", ",")}\n'

    print()
    print(text)
    if options.dump:
        with open('presentations_format_list.txt', 'w') as f:
            f.write(text)

    print()
    print(f'Found {len(analyzer.folders)} folders, {len(analyzer.presentations)} presentations, {len(folder_in_catalogs)} folders linked to a catalog')
    print('{total_importable} / {total_video_count} importable videos ({total_duration_h} hours, {total_size_gb} GB), {total_slides} slides'.format(**encoding_infos))
    print()
    print(encoding_infos['video_types_stats'])
