import os
import logging
import xml.dom.minidom as xml
from pymediainfo import MediaInfo
import requests

from mediasite_migration_scripts.lib.utils import MediasiteSetup


class DataExtractor():

    def __init__(self, config_file=None, debug=False):
        print('Connecting...')
        self.debug = debug
        self.setup = MediasiteSetup(config_file)
        self.mediasite = self.setup.mediasite
        self.download_ckeck = False
        self.download_protection = False

        print('Getting presentations... (take a few minutes)')
        self.presentations = self.mediasite.presentation.get_all_presentations()
        self.folders = self.get_all_folders_infos()
        self.catalogs = self.mediasite.catalog.get_all_catalogs()
        self.all_data = self.extract_mediasite_data()

    def extract_mediasite_data(self, parent_id=None):
        """
        Collect all data from Mediasite platform ordered by folder

        params :
            parent_id : id of the top parent folder where parsing should begin
        returns:
            list ot items containing folders' infos, and
                list of items containing presentations' infos and
                    list of items containing videos and slides metadata
        """
        logging.info('Gathering and ordering all presentations / folders data ')
        if not parent_id:
            parent_id = self.mediasite.folder.root_folder_id

        i = 0
        presentations_folders = list()
        for folder in self.folders:
            if i == 0:
                print(f'Requesting metadata... ({len(self.folders)}folders')
            if i > 1:
                print('Requesting: ', f'[{i}]/[{len(self.folders)}] --', round(i / len(self.folders) * 100, 1), '%', end='\r', flush=True)

            path = self._find_folder_path(folder['id'], self.folders)
            if self._is_folder_to_add(path):
                logging.debug('-' * 50)
                logging.debug('Found folder : ' + path)
                presentations_folders.append({**folder,
                                              'catalogs': self.get_folder_catalogs_infos(folder['id']),
                                              'path': path,
                                              'presentations': self.get_presentations_infos(folder['id'])})
            if i > 50 and self.debug:
                break
            i += 1
        return presentations_folders

    def _find_folder_path(self, folder_id, folders, path=''):
        for folder in folders:
            if folder['id'] == folder_id:
                path += self._find_folder_path(folder['parent_id'], folders, path)
                path += '/' + folder['name']
                return path
        return ''

    def _is_folder_to_add(self, path):
        if self.setup.config.get('mediasite_folders_whitelist'):
            for fw in self.setup.config['mediasite_folders_whitelist']:
                if path.find(fw):
                    return True
            return False
        return True

    def get_presentations_infos(self, folder_id):
        logging.debug(f'Gettings presentations infos for folder: {folder_id}')
        presentations_infos = list()

        for presentation in self.presentations:
            if presentation.get('ParentFolderId') == folder_id:
                logging.debug('-' * 50)
                logging.debug(f'Getting infos for presentation: {presentation.get("Id")}')
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
                    'owner_username': presentation.get('RootOwner', ''),
                    'owner_display_name': owner_infos.get('display_name', ''),
                    'owner_mail': owner_infos.get('mail', ''),
                    'creator': presentation.get('Creator', ''),
                    'other_presenters': self.get_presenters_infos(presentation.get('Id')),
                    'availability': self.mediasite.presentation.get_availability(presentation.get('Id')),
                    'published_status': presentation.get('Status') == 'Viewable',
                    'has_slides_details': has_slides_details,
                    'description': presentation.get('Description', ''),
                    'tags': presentation.get('TagList', ''),
                    'timed_events': [],
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
        for catalog in self.catalogs:
            if folder_id == catalog['LinkedFolderId']:
                infos = {'id': catalog.get('Id'),
                         'name': catalog.get('Name'),
                         'description': catalog.get('Description'),
                         'url': catalog.get('CatalogUrl'),
                         'owner_username': catalog.get('Owner')}
                folder_catalogs.append(infos)
        return folder_catalogs

    def get_user_infos(self, username=str()):
        user_infos = dict()

        user = self.mediasite.user.get_profile_by_username(username)
        if user:
            user_infos = {
                'display_name': user.get('DisplayName'),
                'mail': user.get('Email')
            }

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
        logging.debug(f"Gathering videos infos for presentation : {presentation_id}")

        videos_infos = []
        video = self.mediasite.presentation.get_content(presentation_id, 'OnDemandContent')
        videos_infos = self._get_video_details(video, presentation_id)

        return videos_infos

    def _get_video_details(self, video, presentation_id):
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

            if not self.download_ckeck:
                self.download_protection = self.is_download_protected(video_url)
                self.download_ckeck = True

            if self.download_protection:
                ticket = self.mediasite.content.get_authorization_ticket(presentation_id)
                if ticket:
                    playbackTicket = ticket.get('Id')
                    video_url += f'?playbackTicket={playbackTicket}&AuthTicket={playbackTicket}'

            file_infos = {
                'url': video_url,
                'format': file['ContentMimeType'],
                'size_bytes': int(file['FileLength']),
                'duration_ms': int(file['Length']),
                'is_transcode_source': file['IsTranscodeSource'],
                'encoding_infos': {}
            }

            if file_infos['format'] == 'video/mp4':
                if file.get('ContentEncodingSettingsId'):
                    file_infos['encoding_infos'] = self._get_encoding_infos_from_api(file['ContentEncodingSettingsId'], file_infos['url'])

                if not file_infos.get('encoding_infos'):
                    logging.debug(f"Failed to get video encoding infos from API for presentation: {file['ParentResourceId']}")
                    if file_infos.get('url'):
                        file_infos['encoding_infos'] = self._parse_encoding_infos(file_infos['url'])
                    elif 'LocalUrl' in content_server:
                        logging.debug(f"File stored in local server. A duplicate probably exist on distribution file server. Presentation: {file['ParentResourceId']}")
                    else:
                        logging.warning(f"No distribution url for this video file. Presentation: {file['ParentResourceId']}")

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

    def is_download_protected(self, url):
        with requests.Session() as session:
            protected = True
            with session.get(url, stream=True) as r:
                protected = not r.ok and 400 < r.status_code < 404
        return protected

    def _get_encoding_infos_from_api(self, settings_id, video_url):
        logging.debug(f'Getting encoding infos from api with settings id: {settings_id}')
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
                    logging.debug('Resolution values given by the API may be reversed... switching to MediaInfo.')
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
                logging.debug(f'Failed to parse XML for video encoding settings for settings ID : {settings_id}')
                logging.debug(e)
        return encoding_infos

    def _parse_encoding_infos(self, video_url):
        logging.debug(f'Parsing with MediaInfo lib for: {video_url}')
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
                logging.warning(f'File is not a video: {video_url}')
        except Exception as e:
            logging.debug(f'Video encoding infos could not be parsed for: {video_url}')
            logging.debug(e)

        return encoding_infos

    def get_slides_infos(self, presentation, details=False):
        presentation_id = presentation['id']
        logging.debug(f"Gathering slides infos for presentation: {presentation_id}")

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

            slides_infos['urls'] = slides_urls
            slides_infos['details'] = slides.get('SlideDetails') if details else None

        return slides_infos

    def get_hostname(self):
        api_url = self.setup.config.get("mediasite_base_url")
        hostname = api_url.split('/').pop()
        hostname = '/'.join(hostname)
        return hostname
