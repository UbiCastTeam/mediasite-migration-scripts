#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys
import logging
import shutil

from mediatransfer import MediaTransfer
import mediasite_migration_scripts.utils.common as utils

if __name__ == '__main__':
    def usage(message=''):
        return 'This script is used to import media from mediasite to mediaserver'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument('-q', '--quiet', action='store_true',
                            dest='quiet', default=False,
                            help='print less status messages to stdout.')
        parser.add_argument('-v', '--verbose', action='store_true',
                            dest='verbose', default=False,
                            help='print all status messages to stdout.')
        parser.add_argument('--max-videos', dest='max_videos', default=None,
                            help='specify maximum of videos for upload.')
        parser.add_argument('-cf', '--config-file',
                            dest='config_file', default=None,
                            help='add custom config file.')
        parser.add_argument('-mf', '--mediasite_file',
                            dest='mediasite_file', default=None,
                            help='add custom mediasite data file.')
        return parser.parse_args()

    options = manage_opts()
    utils.set_logger(options=options)

    logger = logging.getLogger(__name__)

    logger.info('----- START SCRIPT' + 50 * '-')
    logger.debug(f'Starting {__file__}')

    mediasite_file = options.mediasite_file
    if mediasite_file is None:
        mediasite_file = 'mediasite_data.json'

    if not os.path.exists(mediasite_file):
        run_import = input('No metadata file. You need to import Mediasite metadata first.\nDo you want to run import ? [y/N] ')
        run_import = run_import.lower()
        if run_import == 'y' or run_import == 'yes':
            args = ' '.join(sys.argv[1:])
            os.system(f'python3 bin/import_data.py {args}')
        else:
            logger.error('--------- Aborted ---------')
            sys.exit(1)

    config_file = 'config.json'
    if options.config_file:
        config_file = options.config_file
    try:
        with open(config_file) as f:
            config = json.load(f)
    except Exception as e:
        logger.debug(e)
        logger.error('Failed to parse config file.')
        logger.error('--------- Aborted ---------')
        sys.exit(1)

    try:
        with open(mediasite_file) as f:
            mediasite_data = json.load(f)
        with open('mediasite_users.json') as f:
            mediasite_users = json.load(f)
    except Exception as e:
        logger.debug(e)
        logger.error('Failed to parse Mediasite metadata')
        logger.error('--------- Aborted ---------')
        sys.exit(1)

    mediatransfer = MediaTransfer(config, mediasite_data, mediasite_users)

    logger.info('Uploading videos...')
    nb_uploaded_medias = mediatransfer.upload_medias(options.max_videos)

    logger.info(f'Upload successful: uploaded {nb_uploaded_medias} medias')

    keep_resources = input('Do you want to keep resources files (videos, slides) downloaded for migration ? [y/N] ')
    if keep_resources != 'y' or keep_resources != 'yes':
        shutil.rmtree('/tmp/mediasite_files/', ignore_errors=True)

    if options.verbose:
        mediaserver_data = mediatransfer.mediaserver_data
        mediaserver_file = 'mediaserver_data.json'
        try:
            with open(mediaserver_file, 'w') as f:
                json.dump(mediaserver_data, f)
        except Exception as e:
            logger.error('Failed to save Mediaserver mapping')
            logger.debug(e)
            sys.exit(1)

    logger.info('----- END SCRIPT ' + 50 * '-' + '\n')
