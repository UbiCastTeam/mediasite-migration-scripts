#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse

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
    logger = utils.set_logger(options)

    import_manager = MediaServerImportManager()