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


def parse_mediasite_date(date_str):
    #2010-05-26T07:16:57Z
    if '.' in date_str:
        # some media have msec included
        #2016-12-07T13:07:27.58Z
        date_str = date_str.split('.')[0] + 'Z'
    return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')


def get_age_days(date_str):
    days = (datetime.now() - parse_mediasite_date(date_str)).days
    return days


class MediasiteSetup():
    def __init__(self, config_data=None):
        extra_data = config_data if config_data else {}
        self.config = self.setup(extra_data)
        self.mediasite = mediasite_controller.controller(self.config)

    def setup(self, config_extra={}):
        try:
            config_data = {
                "mediasite_base_url": config('MEDIASITE_API_URL'),
                "mediasite_api_secret": config('MEDIASITE_API_KEY'),
                "mediasite_api_user": config('MEDIASITE_API_USER'),
                "mediasite_api_pass": config('MEDIASITE_API_PASSWORD'),
                'mediasite_folders_whitelist': config_extra.get('whitelist')
            }

        except KeyError:
            logging.error('No environment file')
        return config_data

    @staticmethod
    def set_logger(options):
        run_path = os.path.dirname(os.path.realpath(__file__))

        current_datetime_string = '{dt.month}-{dt.day}-{dt.year}'.format(dt=datetime.now())
        logging_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging_datefmt = '%m/%d/%Y - %I:%M:%S %p'
        formatter = logging.Formatter(logging_format, datefmt=logging_datefmt)

        logger = logging.getLogger()
        if options.verbose:
            level = logging.DEBUG
        elif options.info:
            level = logging.INFO
        else:
            level = logging.WARNING
        logger.setLevel(level)

        console = logging.StreamHandler()
        console.setFormatter(formatter)

        logs_folder = f'{run_path}/logs/'
        os.makedirs(logs_folder, exist_ok=True)
        logfile_path = os.path.join(logs_folder, f'test_{current_datetime_string}.log')
        logfile = logging.FileHandler(logfile_path)
        logfile.setFormatter(formatter)

        logger.addHandler(logfile)
        logger.addHandler(console)

        return logger
