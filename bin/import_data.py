#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys

from mediasite_migration_scripts.data_extractor import DataExtractor
import mediasite_migration_scripts.utils.common as utils

if __name__ == '__main__':
    def usage(message=''):
        return 'This script is used to extract metadata from mediasite platform'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument('-q', '--quiet', action='store_true',
                            dest='quiet', default=False,
                            help='print only error status messages to stdout.')
        parser.add_argument('-v', '--verbose', action='store_true',
                            dest='verbose', default=False,
                            help='print all status messages to stdout.')
        parser.add_argument('-cf', '--config-file',
                            dest='config_file', action='store_true', default=None,
                            help='add custom config file.')
        parser.add_argument('-mf', '--mediasite_file',
                            dest='mediasite_file', action='store_true', default=None,
                            help='add custom mediasite data file.')

        return parser.parse_args()

    options = manage_opts()
    logger = utils.set_logger(options)

    mediasite_file = options.mediasite_file
    if mediasite_file is None:
        mediasite_file = 'mediasite_data.json'

    try:
        with open(mediasite_file) as f:
            data = json.load(f)
            logger.info(f'{mediasite_file} already found, not fetching catalog data')
    except Exception as e:
        logger.debug(e)

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
            filter_on = input('Do want apply the whitelist filter on metadata import? (for medias, whitelist filter will always be on) [y/N] ').lower()
            if filter_on != 'y' and filter_on != 'yes':
                config['whitelist'] = []

            extractor = DataExtractor(config=config)
            data = extractor.all_data

            with open(mediasite_file, 'w') as f:
                json.dump(data, f)

            with open('mediasite_catalogs.json', 'w') as f:
                json.dump(extractor.linked_catalogs, f)

            with open('mediasite_users.json', 'w') as f:
                json.dump(extractor.users, f)

            logger.info('--------- Data collection finished --------- ')
            failed_count = len(extractor.failed_presentations)
            if failed_count:
                logger.info(f'Failed to collect {failed_count} presentations:')
                print('\n\t'.join(extractor.failed_presentations))
        except Exception as e:
            logger.error(f'Import data failed: {e}')
            sys.exit(1)
