import json
import os
from datetime import datetime
import logging

import mediasite_migration_scripts.utils.common as utils
from mediasite_migration_scripts.ms_client.client import MediaServerClient


MEDIASITE_DATA_FILE = 'tests/mediasite_data_test.json'
MEDIASERVER_DATA_FILE = 'tests/mediaserver_data_test.json'

logger = logging.getLogger(__name__)


def set_logger(*args, **kwargs):
    return utils.set_logger(*args, **kwargs)


def set_test_data():
    new_data = list()
    file = MEDIASITE_DATA_FILE

    if os.path.exists(file):
        with open(file) as f:
            new_data = json.load(f)
    else:
        data = list()
        with open(file) as f:
            data = json.load(f)

        i = 0
        for folder in data:
            presentations = folder['presentations']
            folder['presentations'] = []
            j = 0
            for p in presentations:
                if p['slides']:
                    slides_urls = p['slides']['urls']
                    p['slides']['urls'] = []
                    k = 0
                    for u in slides_urls:
                        p['slides']['urls'].append(u)
                        k += 1
                        if k >= 2:
                            break

                    slides_details = p['slides']['details']
                    if not slides_details:
                        slides_details = []
                    p['slides']['details'] = []
                    x = 0
                    for d in slides_details:
                        p['slides']['details'].append(d)
                        x += 1
                        if x >= 2:
                            break

                folder['presentations'].append(p)
                j += 1
                if j >= 2:
                    break

            new_data.append(folder)

            i += 1
            if i >= 2:
                break

    return new_data


class MediaServerTestUtils():
    def __init__(self, config={}):
        print(config.get('mediaserver_url'))
        self.ms_config = {
            "API_KEY": config.get('mediaserver_api_key'),
            "CLIENT_ID": "mediasite-migration-client",
            "PROXIES": {"http": "",
                        "https": ""},
            "SERVER_URL": config.get('mediaserver_url'),
            "UPLOAD_CHUNK_SIZE": 5242880,
            "VERIFY_SSL": False,
            "LOG_LEVEL": 'WARNING'}
        self.ms_client = MediaServerClient(local_conf=self.ms_config, setup_logging=False)

    def create_test_channel(self):
        test_channel = dict()
        dt = datetime.now()
        test_channel_name = f'test-{dt.month}/{dt.day}/{dt.year}-{dt.hour + 2}:{dt.minute}:{dt.second}'.format()

        test_channel = self.ms_client.api('channels/add', method='post', data={'title': test_channel_name, 'parent': 'c126199c71afcpw7vd1a'})
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
