#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
from pathlib import Path

from mediasite_migration_scripts.data_extractor import DataExtractor
import mediasite_migration_scripts.utils.common as utils

if __name__ == '__main__':
    def usage():
        return 'This script is used to collect metadata from mediasite platform.'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=argparse.RawTextHelpFormatter)
        parser.add_argument('-q', '--quiet',
                            action='store_true',
                            default=False,
                            help='print only error status messages to stdout.')
        parser.add_argument('-v', '--verbose',
                            action='store_true',
                            default=False,
                            help='print all status messages to stdout.')
        parser.add_argument('--config-file',
                            action='store_true',
                            default='config.json',
                            help='add custom config file.')
        parser.add_argument('--mediasite-file',
                            action='store_true',
                            default='mediasite_all_data.json',
                            help='add custom mediasite data file.'),
        parser.add_argument('--failed-csvfile',
                            action='store_true',
                            default='failed.csv',
                            help='add custom mediasite data file.'),
        parser.add_argument('--max-folders',
                            help='specify maximum folders to collect infos'),

        return parser.parse_args()
    options = manage_opts()
    logger = utils.set_logger(options)

    try:
        mst_file_path = Path(options.mediasite_file)

        if mst_file_path.is_file():
            logger.info(f'Found collected data in {mst_file_path}')

            should_collect = input('Do you want to run data collect anyway (collected data will be overwritten) ? [y/N] ')
            if should_collect not in ['y', 'yes']:
                logger.info('Aborting script')
                sys.exit(0)

        config = utils.read_json(options.config_file)
        extractor = DataExtractor(config, options)

        mediasite_data_to_store_attributs = ['all_data', 'linked_catalogs', 'users']
        for data_attr in mediasite_data_to_store_attributs:
            mediasite_filename = ''.join(['mediasite_', data_attr, '.json'])
            utils.write_json(data=getattr(extractor, data_attr), path=mediasite_filename, open_text_option='w')

        logger.info('--------- Data collection finished --------- ')
        failed_count = len(extractor.failed_presentations)
        if failed_count:
            logger.warning(f'Some errors on data collect for {failed_count} presentations. See report in failed.csv')

    except KeyboardInterrupt:
        logger.info('Collect interrupted by user. Not keeping collected data.')
        sys.exit(0)
    except Exception as e:
        logger.error(f'Import data failed: {e}')
        sys.exit(1)
