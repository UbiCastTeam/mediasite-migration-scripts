#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
from argparse import RawTextHelpFormatter
import os
import sys
import logging

from import_manager import MediaServerImportManager
from mediasite_migration_scripts.lib import utils

if __name__ == '__main__':
    def usage(message=''):
        return 'This script is used to extract metadata from mediasite platform'

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
        parser.add_argument('-r', '--remove-all', action='store_true',
                            dest='remove_all', default=False,
                            help='remove all uploaded medias.')

        return parser.parse_args()

    options = manage_opts()
    utils.set_logger(options=options)
    log_level = 'DEBUG' if options.verbose else 'WARNING'
    logger = logging.getLogger(__name__)

    mediasite_file = 'mediasite_data_debug.json' if options.dryrun else 'mediasite_data.json'
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
        print('Import failed')
        exit()

    print('Mapping data for MediaServer...')
    import_manager = MediaServerImportManager(mediasite_data, log_level)

    mediaserver_data = import_manager.mediaserver_data
    mediaserver_file = 'mediaserver_data_debug.json' if options.dryrun else 'mediaserver_data.json'
    try:
        with open(mediaserver_file, 'w') as f:
            json.dump(mediaserver_data, f)
    except Exception as e:
        print('Failed to save Mediaserver metadata')
        logger.debug(e)

    if options.upload:
        print('Uploading videos...')
        import_manager.upload_medias(int(options.max_videos))
    elif options.remove_all:
        print('Removing all videos uploaded...')
        len_removed = import_manager.delete_uploaded_medias()
        print(f'\nRemoved {len_removed} medias')
