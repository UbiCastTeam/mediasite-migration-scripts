import os
import logging
import xml.dom.minidom as xml
from datetime import datetime
import time
from pathlib import Path
from dataclasses import dataclass, asdict, fields
from functools import lru_cache

from mediasite_migration_scripts.assets.mediasite import controller as mediasite_client
import utils.common as utils
import utils.media as media
import utils.http as http
import utils.mediasite as mediasite_utils

logger = logging.getLogger(__name__)


@dataclass
class Failed():
    presentation_id: str
    error: str
    collected: str


class DataExtractor():

    def __init__(self, config, options):
        logger.info('Connecting...')
        self.mediasite_client = mediasite_client.controller(config)
        self.mediasite_client_config = config

        self.session = http.get_session(config['mediasite_api_user'], config['mediasite_api_password'])
        self.max_folders = options.max_folders

        self.fields_to_get = {
            'folders': ['Id', 'ParentFolderId', 'Name', 'Owner', 'Description'],
            'catalogs': ['Id', 'Name', 'Description', 'CatalogUrl', 'Owner', 'CreationDate'],
            'presentations': ['Id', 'Title', 'CreationDate', 'RecordDate', 'Status', 'Private',
                              'Description', 'TagList', 'Streams', '#Play'],
            'presentation_analytics': ['TotalViews', 'LastWatched'],
            'user_types': ['Owner', 'Creator', 'PrimaryPresenter'],
            'users': ['UserName', 'DisplayName', 'Email'],
            'presenters': ['DisplayName'],
            'video_files': ['FileNameWithExtension', 'ContentMimeType', 'FileLength', 'Length', 'IsTranscodeSource'],
            'slides': ['FileNameWithExtension', 'Length', 'SlidesDetails', 'StreamType', 'ContentServerId'],
            'slides_content_server': ['Url']
        }
        self.presentation_videos_endpoint = 'OnDemandContent'
        self.presentation_content_endpoints = ['TimedEvents', 'Presenters', 'SlideContent', 'SlideDetailsContent']

        self.presentations = None
        self.failed_presentations = list()
        self.failed_presentations_errors = {
            'request': 'Requesting Mediasite API gone wrong',
            'slides_video_missing': 'Slides from video are missing (detect slides will be lauch)',
            'slides_jpeg_missing': 'Slides from jpeg are missing',
            'slides_unknown_stream_missing': 'Slides from unkown stream type are missing',
            'slides_timecodes': 'Somes slides timecodes are greater than the video duration',
            'videos_missing': 'All videos are missing',
            'some_videos_missing': 'Some videos are missing',
            'timed_events_timecodes': 'Some timed events / chapters timecodes are greater than the video duration ',
            'videos_composites_missing': 'One video is missing for video composition'
        }
        self.failed_presentations_filename = options.failed_csvfile

        self.users = list()
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
        self.write_csv_report()

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

    def write_csv_report(self):
        fieldnames = [field.name for field in fields(Failed)]
        failed_presentations_dict_rows = [asdict(p) for p in self.failed_presentations]
        try:
            utils.write_csv(self.failed_presentations_filename, fieldnames, failed_presentations_dict_rows)
        except Exception as e:
            logger.error(f'Failed to write csv for failed presentations report: {e}')

    def get_all_presentations(self, already_fetched=False):
        presentations = self.timeit(self.mediasite_client.presentation.get_all_presentations)
        return presentations

    def get_all_catalogs(self):
        all_catalogs = self.timeit(self.mediasite_client.catalog.get_all_catalogs)
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

        if parent_id is None:
            parent_id = self.mediasite_client.folder.root_folder_id

        logger.info('Extracting and ordering metadata.')

        if self.presentations is None:
            self.presentations = self.get_all_presentations()

        for i, folder in enumerate(self.folders):
            if i > 1:
                utils.print_progress_string(i, len(self.folders))

            path = self._find_folder_path(folder['Id'])
            logger.debug('-' * 50)
            logger.debug('Found folder : ' + path)
            catalogs = self.get_folder_catalogs_infos(folder['Id'])
            presentation_infos = self.get_folder_presentations_infos(folder['Id'])
            presentations_folders.append({
                **folder,
                'Catalogs': catalogs,
                'Path': path,
                'Presentations': presentation_infos
            })

            if catalogs:
                self.linked_catalogs.extend(catalogs)

            if self.max_folders and i >= int(self.max_folders):
                break

        return presentations_folders

    def _find_folder_path(self, folder_id, path=''):
        for folder in self.folders:
            if folder['Id'] == folder_id:
                path += self._find_folder_path(folder['ParentFolderId'], path)
                path += '/' + folder['Name']
                return path
        return ''

    def _filter_by_fields_names(self, resource, raw_data):
        fields = dict()
        # TODO: find a better name for 'resource'
        for field in self.fields_to_get[resource]:
            fields[field] = raw_data.get(field)
        return fields

    def get_all_folders_infos(self):
        folders_infos_list = list()
        folders = self.mediasite_client.folder.get_all_folders(self.max_folders)
        for folder in folders:
            folder_infos = self._filter_by_fields_names('folders', folder)
            folders_infos_list.append(folder_infos)

        return folders_infos_list

    def get_folder_catalogs_infos(self, folder_id):
        folder_catalogs = list()
        for catalog in self.all_catalogs:
            if folder_id == catalog.get('LinkedFolderId'):
                catalog_infos = self._filter_by_fields_names('catalogs', catalog)
                folder_catalogs.append(catalog_infos)
        return folder_catalogs

    def get_folder_presentations_infos(self, folder_id):
        folder_presentations_infos = list()
        children_presentations = list()
        # find presentations in folder
        for presentation in self.presentations:
            if presentation.get('ParentFolderId') == folder_id:
                children_presentations.append(presentation)

        logger.debug(f'Gettings infos for {len(children_presentations)} presentations for folder: {folder_id}')

        for p in children_presentations:
            pid = p.get('Id')
            infos = dict()
            try:
                infos = self.get_presentation_infos(p)
            except Exception:
                logger.error(f'Getting presentation info for {pid} failed, sleeping 5 minutes before retrying')
                # time.sleep(5 * 60)
                try:
                    infos = self.get_presentation_infos(p)
                    logger.info(f'Second try for {pid} passed')
                    folder_presentations_infos.append(infos)
                except Exception as e:
                    logger.error(f'Failed to get info for presentation {pid}, moving to the next one: {e}')
                    self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['request'], collected=False))

            if infos and self._to_collect(pid):
                folder_presentations_infos.append(infos)

        return folder_presentations_infos

    def get_presentation_infos(self, presentation):
        presentation_infos = dict()
        pid = presentation['Id']

        logger.debug('-' * 50)
        logger.debug(f"Getting all infos for presentation {pid}")

        presentation_infos = self._filter_by_fields_names('presentations', presentation)

        presentation_infos[self.presentation_videos_endpoint] = videos = self.mediasite_client.presentation.get_content(
            presentation_infos['Id'], self.presentation_videos_endpoint)
        for video_file in presentation_infos[self.presentation_videos_endpoint]:
            video_file['ContentServer'] = self.mediasite_client.content.get_content_server(video_file['ContentServerId'])

        if mediasite_utils.valid_videos_urls_exists(videos, self.session):
            if not self._has_slides_details(presentation):
                self.presentation_content_endpoints.remove('SlideDetailsContent')

            for content_endpoint in self.presentation_content_endpoints:
                presentation_infos[content_endpoint] = self.mediasite_client.presentation.get_content(pid, content_endpoint)

            presentation_analytics = self.mediasite_client.presentation.get_analytics(pid)
            presentation_infos['PresentationAnalytics'] = self._filter_by_fields_names('presentation_analytics', presentation_analytics)

            users_infos = self.get_users_infos(presentation)
            presentation_infos['UserProfiles'] = self._filter_by_fields_names('user_types', users_infos)

            presentation_infos['Presenters'] = self.get_presenters_infos(pid)
            presentation_infos['Availability'] = self.mediasite_client.presentation.get_availability(pid)

        return presentation_infos

    def _has_slides_details(self, presentation):
        for stream_type in presentation.get('Streams'):
            if stream_type.get('StreamType') == 'Slide':
                return True
        return False

    def get_users_infos(self, presentation):
        logger.debug(f"Getting all users infos for presentation {presentation.get('Id')}.")
        users_infos = dict()
        for user_type in self.fields_to_get['user_types']:
            users_infos[user_type] = self._get_user_infos(presentation.get(user_type, ''))

        return users_infos

    @lru_cache
    def _get_user_infos(self, username):
        user_infos = dict()

        if not username.startswith('Default Presenter'):
            logger.debug(f'Getting user info for {username}')

            user = self.mediasite_client.user.get_profile_by_username(username)
            if user:
                user_infos = self._filter_by_fields_names('users', user)

            self.users.append(user_infos)

        return user_infos

    def get_presenters_infos(self, presentation_id):
        presenters_infos = list()

        presenters = self.mediasite_client.presentation.get_presenters(presentation_id)
        if presenters:
            for presenter in presenters:
                presenter_infos = self._filter_by_fields_names('presenters', presenter)
                if not presenter_infos.get('DisplayName', '').startswith('Default Presenter'):
                    presenters_infos.append(presenter_infos)

        return presenters_infos

    def get_videos_infos(self, presentation_infos):
        pid = presentation_infos['Id']
        logger.debug(f'Gathering video info for presentation : {pid}')

        videos_infos = list()
        videos = presentation_infos['OnDemandContent']
        videos_infos, videos_not_found_count, videos_streams_types = self._get_videos_details(videos)

        if len(videos_streams_types) > 1:
            for stream_type in videos_streams_types:
                if stream_type not in [v.get('stream_type') for v in videos_infos]:
                    self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['videos_composites_missing'], collected=False))
                    return []

        if videos_infos and videos_not_found_count:
            self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['some_videos_missing'], collected=True))
            logger.warning(f'{videos_not_found_count} videos files not found for presentation {pid}')
        elif not videos_infos:
            logger.error(f'Failed to get a video file for presentation {pid}, moving to next one')
            self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['videos_missing'], collected=False))

        return videos_infos

    def _get_videos_details(self, videos):
        videos_list = list()
        videos_streams_types = list()
        videos_not_found_count = int()

        for file in videos:
            file_stream_type = file['StreamType']
            if file_stream_type not in videos_streams_types and file_stream_type.startswith('Video'):
                videos_streams_types.append(file_stream_type)

            file_infos = self._filter_by_fields_names('video_files', file)

            file_url = mediasite_utils.get_video_url(file)
            file_found = http.url_exists(file_url, self.session)
            if not file_found:
                logger.warning(f'Video file not found: {file_url}')
                videos_not_found_count += 1
            else:
                if file_infos['ContentMimeType'] == 'video/mp4' or file_infos['ContentMimeType'] == 'video/x-ms-wmv':
                    if file.get('ContentEncodingSettingsId'):
                        file_infos['encoding_infos'] = self._get_encoding_infos_from_api(file['ContentEncodingSettingsId'], file_url)

                    if not file_infos.get('encoding_infos'):
                        logger.debug(f"Video encoding infos not found in API for presentation: {file['ParentResourceId']}")
                        if file_url is not None:
                            file_infos['encoding_infos'] = self._parse_encoding_infos(file_url)
                        else:
                            logger.warning(f"No distribution url for this video file. Presentation: {file['ParentResourceId']}")

                stream_index = self._get_video_stream_index(file_stream_type, videos_list)
                if stream_index is None:
                    videos_list.append({'stream_type': file_stream_type,
                                       'files': [file_infos]})
                else:
                    videos_list[stream_index].append(file_infos)

        return videos_list, videos_not_found_count, videos_streams_types

    def _get_video_stream_index(self, stream_type, videos_list):
        for index, video in enumerate(videos_list):
            if stream_type == video.get('stream_type'):
                return index
        return None

    def _get_encoding_infos_from_api(self, settings_id, video_url):
        logger.debug(f'Getting encoding infos from api with settings id: {settings_id}')
        encoding_infos = {}
        encoding_settings = self.mediasite_client.content.get_content_encoding_settings(settings_id)
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
                media_exists = http.url_exists(video_url)
                if not media_exists:
                    logger.debug(f'Video {video_url} not reachable.')
            except Exception as e:
                logger.debug(e)

        return encoding_infos

    def get_slides_infos(self, presentation_infos):
        pid = presentation_infos['Id']
        logger.debug(f'Gathering slides infos for presentation: {pid}')

        if self._has_slides_details(presentation_infos):
            slide_content_request = 'SlideDetailsContent'
        else:
            slide_content_request = 'SlideContent'

        slides = self.mediasite_client.presentation.get_content(pid, slide_content_request)
        # SlideDetailsContent returns a dict whereas SlideContent return a list (key 'value' in JSON response)
        if type(slides) == list and len(slides) > 0:
            slides = slides[0]

        slides_infos = dict()
        if slides and self._slides_are_correct(slides):
            slides_infos = self._filter_by_fields_names('slides', slides)

            content_server = self.mediasite_client.content.get_content_server(slides.get('ContentServerId', ''), slide=True)
            slides_infos['ContentServer'] = self._filter_by_fields_names('slides_content_server', content_server)

            for s_details in slides_infos.get('SlideDetails', []):
                if not self._is_correct_timecode(s_details['TimeMilliseconds'], presentation_infos):
                    self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['slides_timecodes'], collected=True))
                    slides_infos = {}
                    break

            if not mediasite_utils.slides_urls_exists(presentation_infos):
                slides_stream_type = slides.get('StreamType', '')
                if slides_stream_type == 'Slide':
                    logger.error(f'Slide from jpeg not found for presentation {pid}')
                    self.failed_presentations.append(pid, error=self.failed_presentations_errors['slides_jpeg_missing'], collected=False)
                elif slides_stream_type.startswith('Video'):
                    logger.warning(f'Slide file created from video stream not found for presentation {pid}')
                    logger.warning(f'Detect slides will be lauched for presentation {pid}')
                    self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['slides_video_missing'], collected=True))
                else:
                    logger.error(f'Slide file from unknown stream type [{slides_stream_type}] not found for presentation {pid}')
                    self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['slides_unknown_stream_missing']), collected=False)

        return slides_infos

    def _slides_are_correct(self, slides):
        """
            Check if slides were created from a slides presentation or computer stream.
            Sometimes users use their camera as a stream source by mistake for slides detection.
        """
        encoding_settings = self.mediasite_client.content.get_content_encoding_settings(slides.get('ContentEncodingSettingsId', ''))
        if encoding_settings:
            source = encoding_settings.get('Name', '')
            return (source != '[Default] Use Recorder\'s Settings' and slides.get('SlideDetails'))
        return False

    def get_timed_events(self, presentation_infos):
        timed_events = []
        pid = presentation_infos['Id']
        if pid:
            timed_events_result = self.mediasite_client.presentation.get_content(pid, resource_content='TimedEvents')
            for event in timed_events_result:
                event_infos = dict()
                if event.get('Payload'):
                    try:
                        event_xml = xml.parseString(event['Payload']).documentElement

                        event_position = event.get('Position', 0)
                        if self._is_correct_timecode(event_position, presentation_infos):
                            event_infos['Position'] = event_position
                            event_payload_tags = ['Number', 'Title']
                            for tag in event_payload_tags:
                                event_infos[tag] = event_xml.getElementsByTagName(tag)[0].firstChild.nodeValue
                            timed_events.append(event_infos)
                        else:
                            logger.warning(f'A timed event timecode is greater than the video duration for presentation {pid}')
                            self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['timed_events_timecodes'], collected=True))
                            timed_events = []

                    except Exception as e:
                        logger.debug(f'Failed to get timed event for presentation {pid}: {e}')

        return timed_events

    def _is_correct_timecode(self, timecode, presentation_infos):
        for video in presentation_infos['Videos']:
            for file in video['files']:
                if timecode > file['duration_ms']:
                    return False
        return True

    def download_all_slides(self):
        all_ok = True
        for folder in self.all_data:
            for p_infos in folder.get('Presentations', []):
                self.nb_all_slides += mediasite_utils.get_slides_count(p_infos)
                ok = self._download_presentation_slides(p_infos)
                # if at least one is false, all is false
                all_ok *= ok

        if all_ok:
            logger.info(f'Sucessfully downloaded all slides: [{self.nb_all_slides}]')
        else:
            logger.error(f'Failed to download all slides from Mediasite: [{self.nb_all_downloaded_slides}] / [{self.nb_all_slides}]')
        return all_ok

    def _download_presentation_slides(self, presentation_infos):
        ok = False
        if len(presentation_infos.get('Slides', [])) <= 0:
            ok = True
        else:
            pid = presentation_infos['Id']
            presentation_slides_urls = mediasite_utils.get_slides_urls(presentation_infos)
            if presentation_slides_urls:
                nb_slides_downloaded = 0
                nb_slides = len(presentation_slides_urls)

                presentation_slides_download_folder = self.slides_download_folder / pid
                presentation_slides_download_folder.mkdir(parents=True, exist_ok=True)

                logger.debug(f'Downloading slides for presentation: {pid}')
                for url in presentation_slides_urls:
                    filename = url.split('/').pop()
                    file_path = presentation_slides_download_folder / filename

                    print('Downloading slides : ', end='')
                    utils.print_progress_string(self.nb_all_downloaded_slides, self.nb_all_slides)

                    # do not re-download
                    if file_path.is_file():
                        nb_slides_downloaded += 1
                    else:
                        r = self.session.get(url)
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
                    logger.error(f'Failed to download all slides for presentation {pid}: [{nb_slides_downloaded}] / [{nb_slides}]')

        return ok

    def _to_collect(self, presentation_id):
        for failed_p in self.failed_presentations:
            if failed_p.presentation_id == presentation_id and not failed_p.collected:
                return False
        return True
