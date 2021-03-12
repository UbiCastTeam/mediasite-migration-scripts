#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
from argparse import RawTextHelpFormatter
import os
import sys
import logging

from mediatransfer import MediaTransfer
from mediasite_migration_scripts.lib import utils

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
        parser.add_argument('-f', '--max-folders', dest='max_folders', default=None,
                            help='specify maximum of folders to parse for metadata.')
        parser.add_argument('--max-videos', dest='max_videos', default=None,
                            help='specify maximum of videos for upload.')
        parser.add_argument('-u', '--upload', action='store_true',
                            dest='upload', default=False,
                            help='upload medias.')
        parser.add_argument('-rm', '--remove-medias', action='store_true',
                            dest='remove_medias', default=False,
                            help='remove all uploaded medias.')
        parser.add_argument('-rc', '--remove-channels', action='store_true',
                            dest='remove_channels', default=False,
                            help='remove all uploaded medias.')

        return parser.parse_args()

    options = manage_opts()
    utils.set_logger(options=options)
    log_level = 'DEBUG' if options.verbose else 'WARNING'
    logger = logging.getLogger(__name__)

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

    mediatransfer = MediaTransfer(mediasite_data, log_level)
    mediaserver_data = mediatransfer.mediaserver_data
    mediaserver_file = 'mediaserver_data.json'

    if options.upload:
        print('Uploading videos...')
        max_videos = int(options.max_videos) if options.max_videos else None
        mediatransfer.upload_medias(max_videos)
        try:
            with open(mediaserver_file, 'w') as f:
                json.dump(mediaserver_data, f)
        except Exception as e:
            print('Failed to save Mediaserver metadata')
            logger.debug(e)

    elif options.remove_medias:
        print('Removing all videos uploaded...')
        nb_medias_removed = int()
        try:
            with open(mediaserver_file) as f:
                mediatransfer.mediaserver_data = json.load(f)
        except Exception as e:
            logger.error('No mediaserver metadata file found. Maybe no upload have been made ?')
            logger.debug(e)
            exit()
        medias_removed = mediatransfer.remove_uploaded_medias()
        print(f'\nRemoved {nb_medias_removed} medias')

    elif options.remove_channels:
        print('Removing all channels created...')
        nb_channels_removed = int()
        mediaserver_file = 'tests/mediaserver_data_test.json'
        try:
            with open(mediaserver_file) as f:
                mediatransfer.mediaserver_data = json.load(f)
        except Exception as e:
            logger.error('No mediaserver metadata file found. Maybe no upload have been made ?')
            logger.debug(e)
            exit()
        nb_channel_removed = mediatransfer.remove_channels_created()
