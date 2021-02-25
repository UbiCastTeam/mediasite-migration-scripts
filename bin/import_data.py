#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from argparse import RawTextHelpFormatter
import argparse
import json

from mediasite_migration_scripts.data_extractor import DataExtractor
from mediasite_migration_scripts.lib.mediasite_setup import MediasiteSetup
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

    try:
        with open('config.json') as js:
            config_data = json.load(js)
    except Exception as e:
        logger.debug(e)
        logger.info('No config file or file is corrupted.')
        config_data = None

    file = 'data_debug.json' if options.dryrun else 'data.json'
    try:
        with open(file) as f:
            data = json.load(f)
            logger.info(f'{file} already found, not fetching catalog data')
    except Exception as e:
        logger.debug(e)
        try:
            extractor = DataExtractor(config_data, options.dryrun)
            data = extractor.all_data

            with open(file, 'w') as f:
                json.dump(data, f)

            with open('catalogs.json', 'w') as f:
                json.dump(extractor.catalogs, f)

            print('--------- Import data successfull --------- ')
        except Exception as e:
            print('Import data failed !')
            logger.debug(e)
