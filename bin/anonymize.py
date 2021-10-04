import argparse
import logging

import mediasite_migration_scripts.utils.common as utils
import tests.common as test_utils

logging.getLogger('root').handlers = []
utils.set_logger()
logger = logging.getLogger('__name__')

if __name__ == '__main__':
    def manage_opts():
        parser = argparse.ArgumentParser(description='This script is used to anonymize data for tests')
        parser.add_argument(
            '--data-file',
            default='data/mediasite_all_data.json',
            help='Data file to anonymize'
        ),
        parser.add_argument(
            '--dest',
            default='tests/anon_data.json',
            help='Path destination for anonymized data file'
        ),
        parser.add_argument(
            '--all',
            action='store_true',
            default=False,
            help='Get all data anonmyzed. By default you only get a small sample of anonymized data'
        )
        return parser.parse_args()

    options = manage_opts()

    logger.info(f'Anonymizing data from {options.data_file}')
    data = utils.read_json(options.data_file)
    anon_data = test_utils.anonymize_data(data)
    if not options.all:
        anon_data = test_utils.to_small_data(anon_data)

    utils.write_json(anon_data, options.dest)
