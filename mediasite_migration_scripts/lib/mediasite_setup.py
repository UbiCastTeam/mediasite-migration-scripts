#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
from datetime import datetime
from decouple import config

from mediasite_migration_scripts.assets.mediasite import controller as mediasite_controller


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
