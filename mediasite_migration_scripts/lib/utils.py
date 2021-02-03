#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import json
from datetime import datetime
from decouple import config
import argparse
from argparse import RawTextHelpFormatter

from assets.mediasite import controller as mediasite_controller


class MediasiteSetup():
    def __init__(self):
        self.config = self.setup()
        self.mediasite = mediasite_controller.controller(self.config)

    def setup(self, config_extra={}):
        try:
            config_data = {
                "mediasite_base_url": config('MEDIASITE_API_URL'),
                "mediasite_api_secret": config('MEDIASITE_API_KEY'),
                "mediasite_api_user": config('MEDIASITE_API_USER'),
                "mediasite_api_pass": config('MEDIASITE_API_PASSWORD'),
                'mediasite_folders_whitelist': config_extra.get('MEDIASITE_FOLDERS_WHITELIST')
            }

        except KeyError:
            logging.error('No environment file')
        return config_data

    def set_logger(self, options):
        run_path = os.path.dirname(os.path.realpath(__file__))

        # params
        current_datetime_string = '{dt.month}-{dt.day}-{dt.year}'.format(dt=datetime.now())
        logging_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging_datefmt = '%m/%d/%Y - %I:%M:%S %p'
        formatter = logging.Formatter(logging_format, datefmt=logging_datefmt)

        # level
        logger = logging.getLogger()
        if options.verbose:
            level = logging.DEBUG
        elif options.info:
            level = logging.INFO
        else:
            level = logging.WARNING
        logger.setLevel(level)

        # console
        console = logging.StreamHandler()
        console.setFormatter(formatter)

        # log file
        logs_folder = f'{run_path}/logs/'
        os.makedirs(logs_folder, exist_ok=True)
        logfile_path = os.path.join(logs_folder, f'test_{current_datetime_string}.log')
        logfile = logging.FileHandler(logfile_path)
        logfile.setFormatter(formatter)

        logger.addHandler(logfile)
        logger.addHandler(console)

        return logger