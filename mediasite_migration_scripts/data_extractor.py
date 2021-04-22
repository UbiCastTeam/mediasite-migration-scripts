import os
import logging
import xml.dom.minidom as xml
from pymediainfo import MediaInfo
import json

from mediasite_migration_scripts.assets.mediasite import controller as mediasite_controller
import utils.common as utils

logger = logging.getLogger(__name__)


class DataExtractor():

    def __init__(self, config=dict(), max_folders=None, e2e_tests=False):
        logger.info('Connecting...')
        self.e2e_tests = e2e_tests
        self.config = {
            'mediasite_base_url': config.get('mediasite_api_url'),
            'mediasite_api_secret': config.get('mediasite_api_key'),
            'mediasite_api_user': config.get('mediasite_api_user'),
            'mediasite_api_pass': config.get('mediasite_api_password'),
            'whitelist': config.get('whitelist')
        }
        self.mediasite = mediasite_controller.controller(self.config)

        self.presentations = None
        self.folders = self.get_all_folders_infos()
        self.all_catalogs = self.mediasite.catalog.get_all_catalogs()

        self.users = list()
        self.linked_catalogs = list()
        self.all_data = self.extract_mediasite_data(max_folders=max_folders)

    def extract_mediasite_data(self, parent_id=None, max_folders=None):
        '''
        Collect all data from Mediasite platform ordered by folder

        params :
            parent_id : id of the top parent folder where parsing should begin
        returns:
            list ot items containing folders' infos, and
                list of items containing presentations' infos and
                    list of items containing videos and slides metadata
        '''

        presentations_folders = list()

        if parent_id is None:
            parent_id = self.mediasite.folder.root_folder_id

        if os.path.exists('mediasite_data.json') and not self.e2e_tests:
            try:
                with open('mediasite_data.json') as f:
                    presentations_folders = json.load(f)

                for folder in presentations_folders:
                    self.linked_catalogs.extend(folder.get('catalogs'))
            except Exception as e:
                logger.error('Failed to extract mediasite data from file.')
                logger.debug(e)
        else:
            if self.presentations is None:
                self.presentations = self.mediasite.presentation.get_all_presentations()

            logger.info('Ordering all presentations by folder')
            for i, folder in enumerate(self.folders):
                if i > 1:
                    print(f'Requesting: [{i}]/[{len(self.folders)}] -- {round(i / len(self.folders) * 100, 1)}%', end='\r', flush=True)

                path = self._find_folder_path(folder['id'], self.folders)
                if utils.is_folder_to_add(path, config=self.config):
                    logger.debug('-' * 50)
                    logger.debug('Found folder : ' + path)
                    catalogs = self.get_folder_catalogs_infos(folder['id'])
                    presentations_folders.append({**folder,
                                                  'catalogs': catalogs,
                                                  'path': path,
                                                  'presentations': self.get_presentations_infos(folder['id'])})
                    if catalogs:
                        self.linked_catalogs.extend(catalogs)

                    if max_folders and i >= max_folders:
                        break

        return presentations_folders

    def _find_folder_path(self, folder_id, folders, path=''):
        for folder in folders:
            if folder['id'] == folder_id:
                path += self._find_folder_path(folder['parent_id'], folders, path)
                path += '/' + folder['name']
                return path
        return ''

    def get_presentations_infos(self, folder_id):
        logger.debug(f'Gettings presentations infos for folder: {folder_id}')
        presentations_infos = list()

        for presentation in self.presentations:
            if presentation.get('ParentFolderId') == folder_id:
                logger.debug('-' * 50)
                logger.debug(f"Getting all infos for presentation {presentation.get('Id')}")
                has_slides_details = False
                for stream_type in presentation.get('Streams'):
                    if stream_type.get('StreamType') == 'Slide':
                        has_slides_details = True
                        break

                owner_infos = self.get_user_infos(username=presentation.get('RootOwner', ''))

                presenter_display_name = presentation.get('PrimaryPresenter', '')
                if presenter_display_name.startswith('Default Presenter'):
                    presenter_display_name = None

                infos = {
                    'id': presentation.get('Id', ''),
                    'title': presentation.get('Title', ''),
                    'creation_date': presentation.get('CreationDate', ''),
                    'presenter_display_name': presenter_display_name,
                    'owner_username': owner_infos.get('username', ''),
                    'owner_display_name': owner_infos.get('display_name', ''),
                    'owner_mail': owner_infos.get('mail', ''),
                    'creator': presentation.get('Creator', ''),
                    'other_presenters': self.get_presenters_infos(presentation.get('Id', '')),
                    'availability': self.mediasite.presentation.get_availability(presentation.get('Id', '')),
                    'published_status': presentation.get('Status') == 'Viewable',
                    'has_slides_details': has_slides_details,
                    'description': presentation.get('Description', ''),
                    'tags': presentation.get('TagList', ''),
                    'timed_events': self.get_timed_events(presentation.get('Id', '')),
                    'url': presentation.get('#Play').get('target', ''),
                }
                infos['videos'] = self.get_videos_infos(presentation.get('Id'))
                infos['slides'] = self.get_slides_infos(infos, details=True)

                presentations_infos.append(infos)

        return presentations_infos

    def get_all_folders_infos(self):
        folders_infos = list()
        folders = self.mediasite.folder.get_all_folders()
        for folder in folders:
            folder_info = {
                'id': folder.get('Id'),
                'parent_id': folder.get('ParentFolderId'),
                'name': folder.get('Name'),
                'owner_username': folder.get('Owner'),
                'description': folder.get('Description')
            }
            folders_infos.append(folder_info)

        return folders_infos

    def get_folder_catalogs_infos(self, folder_id):
        folder_catalogs = list()
        for catalog in self.all_catalogs:
            if folder_id == catalog.get('LinkedFolderId'):
                infos = {'id': catalog.get('Id'),
                         'name': catalog.get('Name'),
                         'description': catalog.get('Description'),
                         'url': catalog.get('CatalogUrl'),
                         'owner_username': catalog.get('Owner')}
                folder_catalogs.append(infos)
        return folder_catalogs

    def get_user_infos(self, username=str()):
        logger.debug(f'Getting user infos with username: {username}.')
        user_infos = dict()

        for u in self.users:
            if u.get('username') == username.lower():
                logger.debug(f'User {username} already fetched.')
                user_infos = u
                break

        if not user_infos:
            user = self.mediasite.user.get_profile_by_username(username)
            if user:
                user_infos = {
                    'username': username.lower(),
                    'display_name': user.get('DisplayName'),
                    'mail': user.get('Email').lower()
                }
                self.users.append(user_infos)

        return user_infos

    def get_presenters_infos(self, presentation_id):
        presenters_infos = list()
        presenters = self.mediasite.presentation.get_presenters(presentation_id)
        if presenters:
            for presenter in presenters:
                presenter_name = presenter.get('DisplayName')
                if not presenter_name.startswith('Default Presenter'):
                    presenters_infos.append({'display_name': presenter_name})

        return presenters_infos

    def get_videos_infos(self, presentation_id):
        logger.debug(f'Gathering video info for presentation : {presentation_id}')

        videos_infos = []
        video = self.mediasite.presentation.get_content(presentation_id, 'OnDemandContent')
        videos_infos = self._get_video_details(video)

        return videos_infos

    def _get_video_details(self, video):
        video_list = []

        for file in video:
            content_server = self.mediasite.content.get_content_server(file['ContentServerId'])
            if 'DistributionUrl' in content_server:
                # popping odata query params, we just need the route
                splitted_url = content_server['DistributionUrl'].split('/')
                splitted_url.pop()
                storage_url = '/'.join(splitted_url)
            file_name = file['FileNameWithExtension']
            video_url = os.path.join(storage_url, file_name) if file_name and storage_url else None

            file_infos = {
                'url': video_url,
                'format': file['ContentMimeType'],
                'size_bytes': int(file['FileLength']),
                'duration_ms': int(file['Length']),
                'is_transcode_source': file['IsTranscodeSource'],
                'encoding_infos': {}
            }

            if file_infos['format'] == 'video/mp4' or file_infos['format'] == 'video/x-ms-wmv':
                if file.get('ContentEncodingSettingsId'):
                    file_infos['encoding_infos'] = self._get_encoding_infos_from_api(file['ContentEncodingSettingsId'], file_infos['url'])

                if not file_infos.get('encoding_infos'):
                    logger.debug(f"Video encoding infos not found in API for presentation: {file['ParentResourceId']}")
                    if file_infos.get('url'):
                        file_infos['encoding_infos'] = self._parse_encoding_infos(file_infos['url'])
                    elif 'LocalUrl' in content_server:
                        logger.debug(f"File stored in local server. A duplicate probably exist on distribution file server. Presentation: {file['ParentResourceId']}")
                    else:
                        logger.warning(f"No distribution url for this video file. Presentation: {file['ParentResourceId']}")

            stream = file['StreamType']
            in_list = False
            for v in video_list:
                if stream == v.get('stream_type'):
                    in_list = True
                    v['files'].append(file_infos)
            if not in_list:
                video_list.append({'stream_type': stream,
                                   'files': [file_infos]})
        return video_list

    def _get_encoding_infos_from_api(self, settings_id, video_url):
        logger.debug(f'Getting encoding infos from api with settings id: {settings_id}')
        encoding_infos = {}
        encoding_settings = self.mediasite.content.get_content_encoding_settings(settings_id)
        if encoding_settings:
            try:
                serialized_settings = encoding_settings['SerializedSettings']
                settings_data = xml.parseString(serialized_settings).documentElement
                # Tag 'Settings' is a XML string to be parsed again...
                settings_node = settings_data.getElementsByTagName('Settings')[0]
                settings = xml.parseString(settings_node.firstChild.nodeValue)

                width = int(settings.getElementsByTagName('PresentationAspectX')[0].firstChild.nodeValue)
                height = int(settings.getElementsByTagName('PresentationAspectY')[0].firstChild.nodeValue)
                # sometimes resolution values given by the API are reversed, we use MediaInfo in that case
                if width < height:
                    logger.debug('Resolution values given by the API may be reversed... switching to MediaInfo.')
                    return self._parse_encoding_infos(video_url)

                codecs_settings = settings.getElementsByTagName('StreamProfiles')[0]
                audio_codec = str()
                video_codec = str()
                for element in codecs_settings.childNodes:
                    if element.getAttribute('i:type') == 'AudioEncoderProfile':
                        audio_codec = element.getElementsByTagName('FourCC')[0].firstChild.nodeValue
                        audio_codec = 'AAC' if audio_codec == 'AACL' else audio_codec
                    elif element.getAttribute('i:type') == 'VideoEncoderProfile':
                        video_codec = element.getElementsByTagName('FourCC')[0].firstChild.nodeValue

                encoding_infos = {
                    'video_codec': video_codec,
                    'audio_codec': audio_codec,
                    'width': width,
                    'height': height,
                }
            except Exception as e:
                logger.debug(f'XML could not be parsed for video encoding settings for settings ID : {settings_id}')
                logger.debug(e)
        return encoding_infos

    def _parse_encoding_infos(self, video_url):
        logger.debug(f'Parsing with MediaInfo lib for: {video_url}')
        encoding_infos = {}
        try:
            media_tracks = MediaInfo.parse(video_url, mediainfo_options={'Ssl_IgnoreSecurity': '1'}).tracks
            for track in media_tracks:
                if track.track_type == 'Video':
                    encoding_infos['video_codec'] = 'H264' if track.format == 'AVC' else track.format
                    encoding_infos['height'] = track.height
                    encoding_infos['width'] = track.width
                elif track.track_type == 'Audio':
                    encoding_infos['audio_codec'] = track.format
            if not encoding_infos.get('video_codec'):
                logger.debug(f'File is not a video: {video_url}')
        except Exception as e:
            logger.warning(f'Video encoding infos could not be parsed for: {video_url}')
            logger.debug(e)

        return encoding_infos

    def get_slides_infos(self, presentation, details=False):
        presentation_id = presentation['id']
        logger.debug(f'Gathering slides infos for presentation: {presentation_id}')

        if details and presentation['has_slides_details']:
            option = 'SlideDetailsContent'
        else:
            option = 'SlideContent'

        slides_infos = {}
        slides = self.mediasite.presentation.get_content(presentation_id, option)
        # SlideDetailsContent returns a dict whereas SlideContent return a list (key 'value' in JSON response)
        if type(slides) == list and len(slides) > 0:
            slides = slides[0]
        if slides:
            content_server_id = slides['ContentServerId']
            content_server = self.mediasite.content.get_content_server(content_server_id, slide=True)
            content_server_url = content_server['Url']
            presentation_id = slides['ParentResourceId']

            slides_base_url = f"{content_server_url}/{content_server_id}/Presentation/{presentation_id}"
            slides_urls = []
            slides_files_names = slides['FileNameWithExtension']
            for i in range(int(slides['Length'])):
                # Transform string format (from C# to Python syntax) -> slides_{0:04}.jpg
                file_name = slides_files_names.replace('{0:D4}', f'{i+1:04}')
                link = f'{slides_base_url}/{file_name}'
                slides_urls.append(link)

            slides_infos['stream_type'] = slides.get('StreamType')
            slides_infos['urls'] = slides_urls
            slides_infos['details'] = slides.get('SlideDetails') if details else None

        return slides_infos

    def get_timed_events(self, presentation_id):
        chapters = []
        if presentation_id:
            timed_events = self.mediasite.presentation.get_content(presentation_id, resource_content='TimedEvents')

            for event in timed_events:
                if event.get('Payload'):
                    chapter_xml = xml.parseString(event['Payload']).documentElement
                    chapters.append({
                        'chapter_index': chapter_xml.getElementsByTagName('Number')[0].firstChild.nodeValue,
                        'chapter_title': chapter_xml.getElementsByTagName('Title')[0].firstChild.nodeValue,
                        'chapter_position_ms': event.get('Position', 0)
                    })

        return chapters

    def get_hostname(self):
        api_url = self.setup.config.get('mediasite_base_url')
        hostname = api_url.split('/').pop()
        hostname = '/'.join(hostname)
        return hostname
