import os
import logging
import xml.dom.minidom as xml
import json
import requests
from datetime import datetime
import time
from pathlib import Path


from mediasite_migration_scripts.assets.mediasite import controller as mediasite_controller
import utils.common as utils
import utils.media as media

logger = logging.getLogger(__name__)


class DataExtractor():

    def __init__(self, config=dict(), force_slides_download=None, max_folders=None, e2e_tests=False):
        logger.info('Connecting...')
        self.session = None
        self.max_folders = max_folders
        self.e2e_tests = e2e_tests
        self.config = {
            'mediasite_base_url': config.get('mediasite_api_url'),
            'mediasite_api_secret': config.get('mediasite_api_key'),
            'mediasite_api_user': config.get('mediasite_api_user'),
            'mediasite_api_password': config.get('mediasite_api_password'),
            'whitelist': config.get('whitelist')
        }
        self.mediasite = mediasite_controller.controller(self.config)
        self.mediasite_auth = (self.config.get('mediasite_api_user'), self.config.get('mediasite_api_password'))

        self.presentations = None
        self.failed_presentations = list()
        self.users = list()
        self.skipped_users = list()
        self.linked_catalogs = list()
        self.download_folder = dl = Path(config.get('download_folder', '/downloads'))
        self.slides_download_folder = dl / 'slides'
        self.nb_all_slides = 0
        self.nb_all_downloaded_slides = 0

        self.timeit(self.run)

    def run(self):
        self.folders = self.get_all_folders_infos()
        self.all_catalogs = self.get_all_catalogs()
        self.all_data = self.timeit(self.extract_mediasite_data)
        self.download_all_slides()
        print(f'Skipped users : \n {self.skipped_users}')

    def timeit(self, method):
        before = time.time()
        results = method()
        took_s = int(time.time() - before)
        took_min = int(took_s / 60)

        if results:
            result_count = len(results)
            seconds_per_result = int(took_s / result_count)
            logger.info(f'{method} took {took_min} minutes, found {result_count} items, {seconds_per_result}s per item')
        else:
            logger.info(f'{method} took {took_min} minutes')
        return results

    def get_all_presentations(self, already_fetched=False):
        presentations = self.timeit(self.mediasite.presentation.get_all_presentations)
        return presentations

    def get_all_catalogs(self):
        all_catalogs = self.timeit(self.mediasite.catalog.get_all_catalogs)
        return all_catalogs

    def extract_mediasite_data(self, parent_id=None):
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
        mediasite_data_already_fetched = os.path.exists('mediasite_data.json')

        if parent_id is None:
            parent_id = self.mediasite.folder.root_folder_id

        if mediasite_data_already_fetched:
            try:
                with open('mediasite_data.json') as f:
                    presentations_folders = json.load(f)

                for folder in presentations_folders:
                    self.linked_catalogs.extend(folder.get('catalogs'))
            except Exception as e:
                logger.error('Failed to extract mediasite data from file.')
                logger.debug(e)
        else:
            logger.info('Extracting and ordering metadata.')

            if self.presentations is None:
                self.presentations = self.get_all_presentations()

            for i, folder in enumerate(self.folders):
                if i > 1:
                    print(f'Requesting folders: [{i}]/[{len(self.folders)}] -- {round(i / len(self.folders) * 100, 1)}%', end='\r', flush=True)

                path = self._find_folder_path(folder['id'])
                logger.debug('-' * 50)
                logger.debug('Found folder : ' + path)
                catalogs = self.get_folder_catalogs_infos(folder['id'])
                presentation_infos = self.get_folder_presentations_infos(folder['id'])
                presentations_folders.append({
                    **folder,
                    'catalogs': catalogs,
                    'path': path,
                    'presentations': presentation_infos
                })

                if catalogs:
                    self.linked_catalogs.extend(catalogs)

                if self.max_folders and i >= int(self.max_folders):
                    break

        return presentations_folders

    def _find_folder_path(self, folder_id, path=''):
        for folder in self.folders:
            if folder['id'] == folder_id:
                path += self._find_folder_path(folder['parent_id'], path)
                path += '/' + folder['name']
                return path
        return ''

    def get_folder_presentations_infos(self, folder_id):
        presentations_infos = list()
        children_presentations = list()
        # find presentations in folder
        for presentation in self.presentations:
            if presentation.get('ParentFolderId') == folder_id:
                children_presentations.append(presentation)
        logger.debug(f'Gettings infos for {len(children_presentations)} presentations for folder: {folder_id}')

        for p in children_presentations:
            try:
                infos = self.get_presentation_infos(p)
                presentations_infos.append(infos)
            except Exception:
                pid = p.get('Id')
                logger.error(f'Getting presentation info for {pid} failed, sleeping 5 minutes before retrying')
                # time.sleep(5 * 60)
                try:
                    infos = self.get_presentation_infos(p)
                    logger.info(f'Second try for {pid} passed')
                    presentations_infos.append(infos)
                except Exception as e:
                    logger.error(f'Failed to get info for presentation {pid}, moving to the next one: {e}')
                    self.failed_presentations.append(pid)

        return presentations_infos

    def get_presentation_infos(self, presentation):
        logger.debug('-' * 50)
        logger.debug(f"Getting all infos for presentation {presentation.get('Id')}")

        pid = presentation['Id']
        users_infos = self.get_users_infos(presentation)
        presentation_analytics = self.mediasite.presentation.get_analytics(pid)

        presentation_infos = {
            'id': pid,
            'title': presentation.get('Title', ''),
            'creation_date': self.get_creation_date(presentation),
            'owner': users_infos.get('owner', {}),
            'creator': users_infos.get('creator', {}),
            'primary_presenter': users_infos.get('presenter', {}),
            'other_presenters': self.get_presenters_infos(pid),
            'availability': self.mediasite.presentation.get_availability(pid),
            'status': presentation.get('Status', ''),
            'private': presentation.get('Private'),
            'description': presentation.get('Description', ''),
            'tags': presentation.get('TagList', ''),
            'timed_events': self.get_timed_events(pid),
            'total_views': presentation_analytics.get('TotalViews', ''),
            'last_viewed': presentation_analytics.get('LastWatched', ''),
            'url': presentation.get('#Play').get('target', ''),
            'videos': self.get_videos_infos(presentation.get('Id')),
            'slides': self.get_slides_infos(presentation)
        }

        # we need videos infos before getting slides and chapters in order to check timecodes
        request_details = self._has_slides_details(presentation)
        presentation_infos['slides'] = self.get_slides_infos(presentation_infos, request_details)
        presentation_infos['timed_events'] = self.get_timed_events(presentation_infos)

        return presentation_infos

    def get_all_folders_infos(self):
        folders_infos = list()
        folders = self.mediasite.folder.get_all_folders(self.max_folders)
        for folder in folders:
            folder_info = {
                'id': folder.get('Id', ''),
                'parent_id': folder.get('ParentFolderId', ''),
                'name': folder.get('Name', '').replace('/', '-'),
                'owner_username': folder.get('Owner', ''),
                'description': folder.get('Description', '')
            }
            folders_infos.append(folder_info)

        return folders_infos

    def get_folder_catalogs_infos(self, folder_id):
        folder_catalogs = list()
        for catalog in self.all_catalogs:
            if folder_id == catalog.get('LinkedFolderId'):
                infos = {'id': catalog.get('Id', ''),
                         'name': catalog.get('Name', ''),
                         'description': catalog.get('Description', ''),
                         'url': catalog.get('CatalogUrl', ''),
                         'owner_username': catalog.get('Owner', ''),
                         'creation_date': catalog.get('CreationDate', '0001-12-25T00:00:00').split('.')[0].replace('Z', '')
                         }
                folder_catalogs.append(infos)
        return folder_catalogs

    def get_users_infos(self, presentation):
        logger.debug(f"Getting all users infos for presentation {presentation.get('Id')}.")
        return {
            'owner': self._get_user_infos(presentation.get('RootOwner', '')),
            'presenter': self._get_user_infos(presentation.get('PrimaryPresenter', '')),
            'creator': self._get_user_infos(presentation.get('Creator', '')),
        }

    def _get_user_infos(self, username):
        user_infos = dict()

        if username.startswith('Default Presenter'):
            pass
        elif '&' in username:
            logger.warning(f'"&" in username {username}, skipping. ')
            self.skipped_users.append(username)
        else:
            for u in self.users:
                if u.get('username') == username:
                    logger.debug(f'User {username} already fetched.')
                    user_infos = u
                    break

        if not user_infos:
            logger.debug(f'Getting user info for {username}')
            user_infos = {
                'username': username,
            }
            user = self.mediasite.user.get_profile_by_username(username)
            if user:
                user_infos['display_name'] = user.get('DisplayName')
                user_infos['mail'] = user.get('Email').lower()

            self.users.append(user_infos)

        return user_infos

    def get_creation_date(self, presentation):
        creation_date_str = str()
        mediasite_format_date = '%Y-%m-%dT%H:%M:%S'

        creation_date_str = presentation.get('CreationDate', '0001-12-25T00:00:00.00Z')
        # MediaServer API do not accept microseconds
        if creation_date_str.endswith('Z'):
            creation_date_str = creation_date_str[:-1].split('.')[0]

        if presentation.get('RecordDate', ''):
            creation_date = datetime.strptime(creation_date_str, mediasite_format_date)

            record_date_str = presentation['RecordDate']
            if record_date_str.endswith('Z'):
                record_date_str = record_date_str[:-1].split('.')[0]
            record_date = datetime.strptime(record_date_str, mediasite_format_date)

            creation_date = min([record_date, creation_date])
            creation_date_str = creation_date.strftime(mediasite_format_date)

        return creation_date_str

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
            media_tracks = media.get_tracks(video_url)
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
            logger.debug(f'Failed to get media info for {video_url}. Error: {e}')
            try:
                if self.session is None:
                    self.session = requests.Session()
                response = self.session.head(video_url)
                if not response.ok:
                    logger.debug(f'Video {video_url} not reachable: {response.status_code}, content: {response.text}')
            except Exception as e:
                logger.debug(e)

        return encoding_infos

    def get_slides_infos(self, presentation, request_details=True):
        presentation_id = presentation['Id']
        logger.debug(f'Gathering slides infos for presentation: {presentation_id}')

        if request_details and self._has_slides_details(presentation):
            option = 'SlideDetailsContent'
        else:
            option = 'SlideContent'

        slides_infos = {}
        slides = self.mediasite.presentation.get_content(presentation_id, option)
        # SlideDetailsContent returns a dict whereas SlideContent return a list (key 'value' in JSON response)
        if type(slides) == list and len(slides) > 0:
            slides = slides[0]

        if slides and not self._is_useless_slides(slides):
            content_server_id = slides.get('ContentServerId', '')
            content_server = self.mediasite.content.get_content_server(content_server_id, slide=True)
            content_server_url = content_server.get('Url', '')

            presentation_id = slides.get('ParentResourceId', '')

            slides_base_url = f"{content_server_url}/{content_server_id}/Presentation/{presentation_id}"
            slides_urls = []
            slides_files_names = slides.get('FileNameWithExtension', '')
            for i in range(int(slides.get('Length', '0'))):
                # Transform string format (from C# to Python syntax) -> slides_{0:04}.jpg
                file_name = slides_files_names.replace('{0:D4}', f'{i+1:04}')
                link = f'{slides_base_url}/{file_name}'
                slides_urls.append(link)

            nb_slides = len(slides_urls)
            slides_infos = {
                'stream_type': slides.get('StreamType', ''),
                'length': nb_slides,
                'urls': slides_urls,
                'details': slides.get('SlideDetails') if request_details else None
            }

        return slides_infos

    def _has_slides_details(self, presentation):
        for stream_type in presentation.get('Streams'):
            if stream_type.get('StreamType') == 'Slide':
                return True
        return False

    def _is_useless_slides(self, slides):
        is_useless = False

        encoding_settings = self.mediasite.content.get_content_encoding_settings(slides.get('ContentEncodingSettingsId', ''))
        if encoding_settings:
            source = encoding_settings.get('Name', '')
            is_useless = (source == '[Default] Use Recorder\'s Settings' and not slides.get('SlideDetails'))

        return is_useless

    def download_all_slides(self):
        all_ok = True
        self.nb_all_slides = self.get_nb_all_slides()
        for folder in self.all_data:
            path = self._find_folder_path(folder['id'])
            if utils.is_folder_to_add(path, config=self.config):
                for presentation in folder.get('presentations', []):
                    ok = self._download_slides(presentation.get('id'), presentation['slides'].get('urls', []))
                # if at least one is false, all is false
                all_ok *= ok

        if all_ok:
            logger.info(f'Sucessfully downloaded all slides: [{self.nb_all_slides}]')
        else:
            logger.error(f'Failed to download all slides from Mediasite: [{self.nb_all_downloaded_slides}] / [{self.nb_all_slides}]')
        return all_ok

    def _download_slides(self, presentation_id, presentation_slides_urls):
        ok = False
        nb_slides_downloaded = 0
        nb_slides = len(presentation_slides_urls)

        if self.session is None:
            self.session = requests.Session()

        presentation_slides_download_folder = self.slides_download_folder / presentation_id
        presentation_slides_download_folder.mkdir(parents=True, exist_ok=True)

        logger.debug(f'Downloading slides for presentation: {presentation_id}')
        for url in presentation_slides_urls:
            filename = url.split('/').pop()
            file_path = presentation_slides_download_folder / filename

            print(f'Downloading slides: [{self.nb_all_downloaded_slides}] / [{self.nb_all_slides}] -- {round(self.nb_all_downloaded_slides / self.nb_all_slides * 100, 1)}%',
                  end='\r')

            # do not re-download
            if file_path.is_file():
                nb_slides_downloaded += 1
            else:
                r = self.session.get(url, auth=self.mediasite_auth)
                if r.ok:
                    with open(file_path, 'wb') as f:
                        f.write(r.content)
                    nb_slides_downloaded += 1
                    self.nb_all_downloaded_slides += 1
                else:
                    logger.error(f'Failed to download {url}')

        logger.debug(f'Downloaded [{nb_slides_downloaded}] / [{nb_slides}] slides.')

        ok = (nb_slides_downloaded == nb_slides)
        if not ok:
            logger.error(f'Failed to download all slides for presentation {presentation_id}: [{nb_slides_downloaded}] / [{nb_slides}]')

        return ok

    def get_nb_all_slides(self):
        nb_slides = 0
        for folder in self.all_data:
            path = self._find_folder_path(folder['id'])
            if utils.is_folder_to_add(path, config=self.config):
                for presentation in folder.get('presentations', []):
                    nb_slides += len(presentation['slides'].get('urls', []))
        return nb_slides

    def get_timed_events(self, presentation_id):
        chapters = []
        if presentation_id:
            timed_events = self.mediasite.presentation.get_content(presentation_id, resource_content='TimedEvents')
            for event in timed_events:
                if event.get('Payload'):
                    try:
                        chapter_xml = xml.parseString(event['Payload']).documentElement
                        chapters.append({
                            'chapter_index': chapter_xml.getElementsByTagName('Number')[0].firstChild.nodeValue,
                            'chapter_title': chapter_xml.getElementsByTagName('Title')[0].firstChild.nodeValue,
                            'chapter_position_ms': event.get('Position', 0)
                        })
                    except Exception as e:
                        logger.debug(f'Non valid chapter: {e}')

        return chapters

    def get_hostname(self):
        api_url = self.setup.config.get('mediasite_base_url')
        hostname = api_url.split('/').pop()
        hostname = '/'.join(hostname)
        return hostname
