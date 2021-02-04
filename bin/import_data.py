from argparse import RawTextHelpFormatter
import argparse
import os
import json
import logging

from data_extractor import DataExtractor
from lib.utils import MediasiteSetup

if __name__ == '__main__':

    # --------------------------- Setup
    # args
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

    #--------------------------- Script
    try:
        with open('config.json') as js:
            config_data = json.load(js)
    except Exception as e:
        logging.debug(e)
        config_data = None

    extractor = DataExtractor(config_data)
    logger = MediasiteSetup.set_logger(options)

    # Listing folders with their presentations
    try:
        with open('data.json') as f:
            data = json.load(f)
            logging.info('data.json already found, not fetching catalog data')
    except Exception as e:
        logging.debug(e)
        data = extractor.order_presentations_by_folder()
        with open('data.json', 'w') as f:
            json.dump(data, f)
