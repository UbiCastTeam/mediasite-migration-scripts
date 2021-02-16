#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from argparse import RawTextHelpFormatter
import argparse
import json

from mediasite_migration_scripts.data_extractor import DataExtractor
from mediasite_migration_scripts.lib.utils import MediasiteSetup

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
    logger = MediasiteSetup.set_logger(options)

    try:
        with open('config.json') as js:
            config_data = json.load(js)
    except Exception as e:
        logger.debug(e)
        logger.info('No config file or file is corrupted.')
        config_data = None

    try:
        with open('data.json') as f:
            data = json.load(f)
            logger.info('data.json already found, not fetching catalog data')
    except Exception as e:
        logger.debug(e)
        extractor = DataExtractor(config_data)
        data = extractor.all_data
        with open('data.json', 'w') as f:
            json.dump(data, f)

        with open('catalogs.json', 'w') as f:
            json.dump(extractor.catalogs, f)

        print('--------- Import data successfull --------- ')
