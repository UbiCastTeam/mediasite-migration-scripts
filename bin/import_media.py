#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
from argparse import RawTextHelpFormatter
import os
import sys

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

        return parser.parse_args()

    options = manage_opts()
    logger = utils.set_logger(options=options)
    log_level = 'DEBUG' if options.verbose else 'WARNING'

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
    import_manager = MediaServerImportManager(mediasite_data, log_level=log_level)
    import_manager.upload_videos()
    mediaserver_data = import_manager.mediaserver_data
    mediaserver_file = 'mediaserver_data_debug.json' if options.dryrun else 'mediaserver_data.json'
    try:
        with open(mediaserver_file, 'w') as f:
            json.dump(mediaserver_data, f)
    except Exception as e:
        print('Failed to save Mediaserver metadata')
        logger.debug(e)
