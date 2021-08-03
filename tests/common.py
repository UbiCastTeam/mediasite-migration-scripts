import json
import os
from datetime import datetime
import logging
from copy import copy

import mediasite_migration_scripts.utils.common as utils
from mediasite_migration_scripts.ms_client.client import MediaServerClient


MEDIASITE_DATA_FILE = 'tests/mediasite_data_test.json'
MEDIASERVER_DATA_FILE = 'tests/mediaserver_data_test.json'

MEDIASERVER_DATA_E2E_FILE = 'tests/e2e/mediaserver_data_e2e.json'
MEDIASITE_USERS_FILE = 'tests/e2e/mediasite_users_test.json'
MEDIASERVER_USERS_FILE = 'tests/e2e/mediaserver_users_test.json'

logger = logging.getLogger(__name__)


def set_logger(*args, **kwargs):
    return utils.set_logger(*args, **kwargs)


def anonymize_data(data):
    fields_to_anonymize = [
        'Title',
        'Name',
        'Owner',
        'Creator',
        'PrimaryPresenter',
        'DisplayName',
        'Email',
        'UserName',
        'ParentFolderName'
    ]

    anon_data = copy(data)
    if isinstance(anon_data, dict):
        for key, val in anon_data.items():
            if isinstance(val, dict) or isinstance(val, list):
                anon_data[key] = anonymize_data(val)
            elif isinstance(val, str):
                if key in fields_to_anonymize:
                    anon_data[key] = f'anon {key}'
                elif 'http' and '://' in val:
                    anon_data[key] = 'https://anon.com/fake'
    elif isinstance(anon_data, list):
        for i, item in enumerate(anon_data):
            anon_data[i] = anonymize_data(item)

    return anon_data


class MediaServerTestUtils():
    def __init__(self, config={}):
        self.ms_config = {
            "API_KEY": config.get('mediaserver_api_key'),
            "CLIENT_ID": "mediasite-migration-client",
            "SERVER_URL": config.get('mediaserver_url'),
            "VERIFY_SSL": False,
            "LOG_LEVEL": 'WARNING'}
        self.ms_client = MediaServerClient(local_conf=self.ms_config, setup_logging=False)

    def create_test_channel(self):
        test_channel = dict()
        dt = datetime.now()
        test_channel_name = f'test-{dt.month}/{dt.day}/{dt.year}-{dt.hour + 2}:{dt.minute}:{dt.second}'.format()

        # Parent E2E test channel : https://beta.ubicast.net/channels/#mediasite-e2e-tests
        test_channel = self.ms_client.api('channels/add', method='post', data={'title': test_channel_name, 'parent': 'c12619b455e75glxvuja'})
        self.ms_client.session.close()

        return test_channel

    def remove_media(self, media=dict()):
        delete_completed = False
        nb_medias_removed = 0

        oid = media.get('ref', {}).get('oid')
        if oid:
            result = self.ms_client.api('medias/delete',
                                        method='post',
                                        data={'oid': oid, 'delete_metadata': True, 'delete_resources': True},
                                        ignore_404=True)
            if result:
                if result.get('success'):
                    logger.debug(f'Media {oid} removed.')
                    delete_completed = True
                    nb_medias_removed += 1
                else:
                    logger.error(f'Failed to delete media: {oid} / Error: {result.get("error")}')
            elif not result:
                logger.warning(f'Media not found in Mediaserver for removal with oid: {oid}. Searching with title.')
            else:
                logger.error(f'Something gone wrong when trying remove media {oid}')

        if not delete_completed:
            title = media['data']['title']
            media = self.ms_client.api('medias/get', method='get', params={'title': title}, ignore_404=True)
            while media and media.get('success'):
                oid = media.get('info').get('oid')
                result = self.ms_client.api('medias/delete',
                                            method='post',
                                            data={'oid': oid, 'delete_metadata': True, 'delete_resources': True},
                                            ignore_404=True)
                if result:
                    logger.debug(f'Media {oid} removed.')
                    nb_medias_removed += 1
                media = self.ms_client.api('medias/get', method='get', params={'title': title}, ignore_404=True)
            if media and not media.get('success'):
                logger.error(f'Failed to delete media: {oid} / Error: {result.get("error")}')

        return nb_medias_removed

    def remove_channel(self, channel_title=None, channel_oid=None):
        ok = False
        if not channel_oid and not channel_title:
            logger.error('Request to remove channel but no channel provided (title or oid)')
        elif not channel_oid and channel_title:
            result = self.ms_client.api('channels/get', method='get', params={'title': channel_title}, ignore_404=True)
            if result:
                channel_oid = result.get('info', {}).get('oid')
            else:
                logger.error('Channel not found for removing')

        if channel_oid:
            result = self.ms_client.api('channels/delete', method='post', data={'oid': channel_oid, 'delete_content': 'yes', 'delete_resources': 'yes'})
            ok = result.get('success')
        else:
            logger.error(f'Something gone wrong when removing channel. Title: {channel_title} / oid: {channel_oid}')

        return ok
