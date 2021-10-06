import logging
from datetime import datetime

from mediasite_migration_scripts.ms_client.client import MediaServerClient

logger = logging.getLogger(__name__)


def parse_mediaserver_date(date_str):
    date_format = '%Y-%m-%d %H:%M:%S'
    return datetime.strptime(date_str, date_format)


class MediaServerUtils():
    def __init__(self, config={}):
        self.ms_config = {
            "API_KEY": config.get('mediaserver_api_key'),
            "CLIENT_ID": "mediasite-migration-client",
            "SERVER_URL": config.get('mediaserver_url'),
            "VERIFY_SSL": False,
            "LOG_LEVEL": 'WARNING'}
        self.ms_client = MediaServerClient(local_conf=self.ms_config, setup_logging=False)

    def remove_media(self, media=dict()):
        delete_completed = False
        nb_medias_removed = 0

        oid = media.get('ref', {}).get('media_oid')
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

    def remove_channel(self, title=None, oid=None):
        ok = False
        if not oid and not title:
            logger.error('Request to remove channel but no channel provided (title or oid)')
        elif not oid and title:
            result = self.ms_client.api('channels/get', method='get', params={'title': title}, ignore_404=True)
            if result:
                oid = result.get('info', {}).get('oid')
            else:
                logger.error('Channel not found for removing')

        if oid:
            result = self.ms_client.api('channels/delete', method='post', data={'oid': oid, 'delete_content': 'yes', 'delete_resources': 'yes'})
            ok = result.get('success')
        else:
            logger.error(f'Something gone wrong when removing channel. Title: {title} / oid: {oid}')

        return ok
