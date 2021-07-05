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
        parser.add_argument('-mf', '--mediasite-file',
                            dest='mediasite_file', action='store_true', default='mediasite_data.json',
                            help='add custom mediasite data file.')
        parser.add_argument('--max-folders', dest='max_folders', default=None,
                            help='specify maximum folders to collect infos'),
        parser.add_argument('--force-slides-download', '-fdl', dest='force_slides_download',
                            action='store_true', default=None,
                            help='Force slides download even if there\'s mediasite data file.')

        return parser.parse_args()

    options = manage_opts()
    logger = utils.set_logger(options)

    mediasite_file = options.mediasite_file
    try:
        with open(mediasite_file) as f:
            data = json.load(f)
            logger.info(f'{mediasite_file} already found, not fetching data.')
            if options.force_slides_download:
                logger.info('Force slides download.')
            else:
                logger.info('Aborting script.')
                sys.exit(0)
    except Exception as e:
        logger.debug(e)
    finally:
        config_file = 'config.json'
        if options.config_file:
            config_file = options.config_file
        try:
            with open(config_file) as f:
                config = json.load(f)
        except Exception as e:
            logger.debug(e)
            logger.error('Failed to parse config file.')
            sys.exit(1)

    try:
        # all data must be feched in order to avoid skipping important data
        # lets ignore any whitelist
        # config['whitelist'] = []
        # whitelist is needed to avoid downloading useless slides

        extractor = DataExtractor(config=config, max_folders=options.max_folders, force_slides_download=options.force_slides_download)
        data = extractor.all_data
        with open(mediasite_file, 'x') as f:
            json.dump(data, f)

        with open('mediasite_catalogs.json', 'x') as f:
            json.dump(extractor.linked_catalogs, f)

        with open('mediasite_users.json', 'x') as f:
            json.dump(extractor.users, f)

        with open('mediasite_failed_presentations.json', 'w') as f:
            json.dump(extractor.failed_presentations, f)

    except FileExistsError:
        pass
    except Exception as e:
        logger.error(f'Import data failed: {e}')
        sys.exit(1)
    finally:
        logger.info('--------- Data collection finished --------- ')
        failed_count = len(extractor.failed_presentations)
        if failed_count:
            logger.info(f'Some errors on collect for {failed_count} presentations:')
            for p in extractor.failed_presentations:
                row = f'{p.presentation_id} | {p.reason} | Collected: {p.collected}'
                sep = '-' * len(row)
                print(sep)
                print(row)
