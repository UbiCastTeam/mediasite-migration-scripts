import logging
import json
import os

from mediasite_migration_scripts.lib import utils
from mediasite_migration_scripts.data_analyzer import DataAnalyzer
from mediasite_migration_scripts.lib.mediaserver_setup import MediaServerSetup


logger = logging.getLogger(__name__)


class MediaTransfer():
    def __init__(self, mediasite_data, ms_log_level='WARNING'):
        self.mediasite_data = mediasite_data
        self.catalogs = self._set_catalogs()
        self.presentations = self._set_presentations()
        self.formats_allowed = self._set_formats_allowed()

        self.ms_setup = MediaServerSetup(log_level=ms_log_level)
        self.ms_client = self.ms_setup.ms_client
        self.root_channel = self.get_root_channel()
        self.mediaserver_data = self.to_mediaserver_keys()

    def upload_medias(self, max_videos=None):
        self.mediaserver_data = self.to_mediaserver_keys()
        logger.debug(f'{len(self.mediaserver_data)} medias found for uploading.')
        logger.debug('Uploading videos')

        nb_medias_uploaded = 0
        for index, media in enumerate(self.mediaserver_data):
            if max_videos and index >= max_videos:
                break
            print('Uploading:', index, '/', len(self.mediaserver_data), f'-- {int(100 * (index/len(self.mediaserver_data)))}%', end='\r')
            channel_path = media['ref']['channel_path']
            channel_oid = self.create_channel(channel_path)
            if not channel_oid:
                del media['data']['channel']
                channel_oid, media['data']['channel'] = self.root_channel

            result = self.ms_client.api('medias/add', method='post', data=media['data'])
            if result.get('success'):
                media['ref'] = {
                    'media_oid': result.get('oid'),
                    'slug': result.get('slug'),
                    'channel_oid': channel_oid,
                    'channel_path': channel_path
                }
                nb_medias_uploaded += 1
            else:
                logger.error(f'Failed to upload media: {media["title"]}')
        return nb_medias_uploaded

    def remove_uploaded_medias(self):
        logger.debug('Deleting medias uploaded')

        medias = self.mediaserver_data
        nb_medias_removed = int()
        for i, m in enumerate(medias):
            print('Removing:', i, '/', len(medias), f'-- {int(100 * (i/len(medias)))}%', end='\r')

            nb_medias_removed += self.remove_media(m)
        return nb_medias_removed

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

    def create_channel(self, channel_path):
        logger.debug(f'Creating channel path: {channel_path}')

        channels_oids = list()
        tree = channel_path.split('/')
        # tree[0] is a empty string because the path start with '/'
        tree.pop(0)

        result = self._create_channel(self.root_channel.get('oid'), tree[0])
        channels_oids.append(result.get('oid'))
        logger.debug(f'Channel created with oid: {result.get("oid")}')

        i = 1
        while result.get('success') and i < len(tree):
            result = self._create_channel(channels_oids[i - 1], tree[i])
            logger.debug(f'Channel created with oid: {result.get("oid")}')
            channels_oids.append(result.get('oid'))
            i += 1
        if i < len(tree):
            logger.error('Failed to construct channel path')
        return channels_oids

    def _create_channel(self, parent_channel, channel):
        logger.debug(f'Creating channel {channel} with parent {parent_channel}')

        result = self.ms_client.api('channels/add', method='post', data={'title': channel, 'parent': parent_channel})
        if result and not result.get('success'):
            logger.error(f'Failed to create channel: {channel} / Error: {result.get("error")}')
        elif not result:
            logger.error(f'No response from API when creating channel: {channel}')
        else:
            return result

    def remove_channels_created(self):
        logger.debug('Deleting channels created')
        medias = self.mediaserver_data
        nb_channels_removed = 0
        for i, m in enumerate(medias):
            print('Removing:', i, '/', len(medias), f'-- {int(100 * (i/len(medias)))}%', end='\r')
            channel_oid = m.get('ref').get('channel_oid')
            if not channel_oid:
                channel_title = m.get('ref').get('channel_path').split('/')[2]
                channel = self.ms_client.api('channels/get', method='get', params={'title': channel_title}, ignore_404=True)
                if not channel:
                    continue
                channel_oid = channel.get('info').get('oid')

            result = self.ms_client.api('channels/delete', method='post', data={'oid': channel_oid, 'delete_content': True, 'delete_resources': True}, ignore_404=True)
            if result and not result.get('success'):
                logger.error(f'Failed to delete channel: {channel_oid} / Error: {result.get("error")}')
            elif not result:
                logger.error(f'Failed to delete channel: {channel_oid} / No message error')
            if result:
                logger.debug(f'Deleted {channel_oid}')
                nb_channels_removed += 1
        return nb_channels_removed

    def to_mediaserver_keys(self):
        logger.debug('Matching Mediasite data to MediaServer keys mapping.')

        mediaserver_data = list()
        if hasattr(self, 'mediaserver_data'):
            mediaserver_data = self.mediaserver_data
        else:
            logger.debug('No data file found for Mediaserver mapping. Generating mapping.')
            for folder in self.mediasite_data:
                for presentation in folder['presentations']:
                    presenter = f"Primary presenter: {presentation['presenter_display_name']}" if presentation.get("presenter_display_name") else ''
                    other_presenters = '\nOther presenters:' if presentation.get('other_presenters') else ''
                    for other_p in presentation['other_presenters']:
                        if not other_p == presenter:
                            other_presenters += f", {other_p['display_name']}"
                    description_text = '' if presentation['description'] is None else f"\n{presentation['description']}"
                    description = f'{presenter}{other_presenters}{description_text}'

                    video_url = None
                    for v in presentation.get('videos')[0]['files']:
                        if self.formats_allowed.get('mp4') and v['format'] == 'video/mp4':
                            video_url = v['url']
                            break
                        elif self.formats_allowed.get('wmv') and v['format'] == 'video/x-ms-wmv':
                            video_url = v['url']
                            break
                    data = {
                        'title': presentation['title'],
                        'channel': folder['name'],
                        'creation': presentation['creation_date'],
                        'speaker_id': presentation['owner_username'],
                        'speaker_name': presentation['owner_display_name'],
                        'speaker_email': presentation['owner_mail'].lower(),
                        'validated': 'yes' if presentation['published_status'] else 'no',
                        'description': description,
                        'keywords': ','.join(presentation['tags']),
                        'slug': 'mediasite-' + presentation['id'],
                        'file_url': video_url,
                        'external_data': json.dumps(presentation)
                    }
                    mediaserver_data.append({'data': data, 'ref': {'channel_path': folder['path']}})
        return mediaserver_data

    def get_root_channel(self, **kwargs):
        oid = str()
        try:
            with open('config.json') as f:
                config = json.load(f)
            oid = config.get('mediaserver_parent_channel')
        except Exception as e:
            logger.error('No parent channel configured. See in config.json.')
            logger.debug(e)
            exit()

        root_channel = dict()
        root_channel = self.ms_client.api('channels/get', method='get', params={'oid': oid}, ignore_404=True)
        if root_channel and root_channel.get('success'):
            root_channel = root_channel.get('info')
        else:
            logger.error('Root channel does not exist. Please provide an existing channel oid in config.json')
        return root_channel

    def _set_formats_allowed(self):
        formats = dict()
        try:
            with open('config.json') as f:
                config = json.load(f)
            formats = config.get('videos_formats_allowed')
        except Exception as e:
            logger.debug(e)
            logger.info('No config file. Settings set to default (all folder, all medias)')
        return formats

    def _set_catalogs(self):
        catalogs = list()
        for folder in self.mediasite_data:
            catalogs.extend(folder.get('catalogs'))
        return catalogs

    def _set_presentations(self):
        presentations = []
        for folder in self.mediasite_data:
            for p in folder['presentations']:
                presentations.append(p)
        return presentations
