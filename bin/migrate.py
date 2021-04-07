#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
from argparse import RawTextHelpFormatter
import os
import sys
import logging

from mediatransfer import MediaTransfer
import mediasite_migration_scripts.utils.common as utils

if __name__ == '__main__':
    def usage(message=''):
        return 'This script is used to import media from mediasite to mediaserver'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=RawTextHelpFormatter)
        parser.add_argument('-i', '--info', action='store_true',
                            dest='info', default=False,
                            help='print more status messages to stdout.')
        parser.add_argument('-v', '--verbose', action='store_true',
                            dest='verbose', default=False,
                            help='print all status messages to stdout.')
        parser.add_argument('-d', '--dry-run', action='store_true',
                            dest='dryrun', default=False,
                            help='not really import medias.')
        parser.add_argument('-f', '--max-folders', dest='max_folders', default=0,
                            help='specify maximum of folders to include for migration.')
        parser.add_argument('--max-videos', dest='max_videos', default=0,
                            help='specify maximum of videos for upload.')
        parser.add_argument('-cf', '--config-file',
                            dest='config_file', action='store_true', default=None,
                            help='add custom config file.')

        return parser.parse_args()

    options = manage_opts()
    utils.set_logger(options=options)
    log_level = 'DEBUG' if options.verbose else 'WARNING'
    logger = logging.getLogger(__name__)

    logger.info('----- START SCRIPT' + 50 * '-')
    logger.debug(f'Starting {__file__}')

    mediasite_file = 'mediasite_data.json'
    if not os.path.exists(mediasite_file):
        run_import = input('No metadata file. You need to import Mediasite metadata first.\nDo you want to run import ? [y/N] ')
        run_import = run_import.lower()
        if run_import == 'y' or run_import == 'yes':
            args = ' '.join(sys.argv[1:])
            os.system(f'python3 bin/import_data.py {args}')
        else:
            print('--------- Aborted ---------')
            exit()

    try:
        with open(mediasite_file) as f:
            mediasite_data = json.load(f)
    except Exception as e:
        logger.debug(e)
        print('Importing data failed')
        exit()

    config_file = 'config.json'
    if options.config_file:
        config_file = options.config_file
    try:
        with open(config_file) as f:
            config = json.load(f)
    except Exception as e:
        logger.critical('Failed to parse config file.')
        logger.debug(e)
        print('--------- Aborted ---------')
        exit()

    mediatransfer = MediaTransfer(mediasite_data=mediasite_data, log_level)
    mediaserver_file = 'mediaserver_data.json'

    print('Uploading videos...')
    max_videos = int(options.max_videos) if options.max_videos else None
    nb_uploaded_medias = mediatransfer.upload_medias(max_videos)
    print('--------- Upload successful ---------')
    print(f' \nUploaded {nb_uploaded_medias} medias')

    mediaserver_data = mediatransfer.mediaserver_data
    try:
        with open(mediaserver_file, 'w') as f:
            json.dump(mediaserver_data, f)
    except Exception as e:
        print('Failed to save Mediaserver mapping')
        logger.debug(e)

    logger.info('----- END SCRIPT ' + 50 * '-' + '\n')
