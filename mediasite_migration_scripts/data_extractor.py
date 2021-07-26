import logging
import time
from pathlib import Path
from dataclasses import dataclass, asdict, fields
from functools import lru_cache

from mediasite_migration_scripts.assets.mediasite import controller as mediasite_client
import utils.common as utils
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

        self.should_filter_resources_data = True
        self.data_fields_to_filter = {
            'Folders': ['Id', 'ParentFolderId', 'Name', 'Owner', 'Description'],
            'Catalogs': ['Id', 'Name', 'Description', 'CatalogUrl', 'Owner', 'CreationDate'],
            'Presentations': ['Id', 'Title', 'CreationDate', 'RecordDate', 'Owner', 'Creator', 'PrimaryPresenter', 'Status', 'Private',
                              'Description', 'TagList', 'Streams', '#Play']
        }
        self.users_types_to_fetch = ['Creator', 'Owner', 'PrimaryPresenter']
        self.presentation_videos_endpoint = 'OnDemandContent'
        self.presentation_content_endpoints = ['TimedEvents', 'Presenters']

        self.presentations = None
        self.failed_presentations = list()
        self.failed_presentations_errors = {
            'request': 'Requesting Mediasite API gone wrong',
            'slides_video_missing': 'Slides from video are missing (detect slides will be lauch)',
            'slides_jpeg_missing': 'Slides from jpeg are missing',
            'slides_unknown_stream_missing': 'Slides from unkown stream type are missing',
            'slides_timecodes': 'Somes slides timecodes are greater than the video duration',
            'videos_missing': 'All videos are missing',
            'composites_videos_missing': 'One video is missing for video composition',
            'some_videos_missing': 'Some videos are missing',
            'timed_events_timecodes': 'Some timed events / chapters timecodes are greater than the video duration ',
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

    def extract_mediasite_data(self, parent_id=None, filtered=True):
        '''
        Collect all data from Mediasite platform ordered by folder.
        Folders, presentations, and catalogs data fields will be filtered by default unless filtered is false

        params :
            parent_id : id of the top parent folder where parsing should begin
        returns:
                Raw data ordered by folder
        '''

        presentations_folders = list()

        if parent_id is None:
            parent_id = self.mediasite_client.folder.root_folder_id

        logger.info('Extracting and ordering metadata.')

        self.get_resources()

        for i, folder in enumerate(self.folders):
            if i > 1:
                utils.print_progress_string(i, len(self.folders))

            logger.debug('-' * 50)
            logger.debug(f"Found folder : {folder['Name']}")
            catalogs = self.get_folder_catalogs(folder['Id'])
            presentation_data = self.get_folder_presentations(folder['Id'])
            presentations_folders.append({
                **folder,
                'Catalogs': catalogs,
                'Presentations': presentation_data
            })
            if catalogs:
                self.linked_catalogs.extend(catalogs)

            if self.max_folders and i >= int(self.max_folders):
                break

        return presentations_folders

    def get_resources(self):
        self.folders = self.mediasite_client.folder.get_all_folders(self.max_folders)
        self.catalogs = self.get_all_catalogs()
        self.presentations = self.get_all_presentations()

        if self.should_filter_resources_data:
            for resource_name, data_fieldsnames in self.data_fields_to_filter.items():
                attr = resource_name.lower()
                for element in getattr(self, attr):
                    setattr(self, attr, mediasite_utils.filter_by_fields_names(element, data_fieldsnames))


    def get_folder_catalogs(self, folder_id):
        folder_catalogs = list()
        for catalog in self.all_catalogs:
            if folder_id == catalog.get('LinkedFolderId'):
                folder_catalogs.append(catalog)
        return folder_catalogs

    def get_folder_presentations(self, folder_id):
        folder_presentations = list()
        children_presentations = list()
        # find presentations in folder
        for presentation in self.presentations:
            if presentation.get('ParentFolderId') == folder_id:
                children_presentations.append(presentation)

        logger.debug(f'Gettings infos for {len(children_presentations)} presentations for folder: {folder_id}')

        for p in children_presentations:
            pid = p.get('Id')
            presentation_resources = dict()
            try:
                presentation_resources = self.get_presentation_resources(p)
            except Exception:
                logger.error(f'Getting presentation info for {pid} failed, sleeping 5 minutes before retrying')
                # time.sleep(5 * 60)
                try:
                    presentation_resources = self.get_presentation_resources(p)
                    logger.info(f'Second try for {pid} passed')
                    folder_presentations.append(presentation_resources)
                except Exception as e:
                    logger.error(f'Failed to get info for presentation {pid}, moving to the next one: {e}')
                    self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['request'], collected=False))

            if presentation_resources and self._to_collect(pid):
                folder_presentations.append(presentation_resources)

        return folder_presentations

    def _to_collect(self, presentation_id):
        for failed_p in self.failed_presentations:
            if failed_p.presentation_id == presentation_id and not failed_p.collected:
                return False
        return True

    def get_presentation_resources(self, presentation):
        pid = presentation['Id']

        logger.debug('-' * 50)
        logger.debug(f"Getting resources for presentation {pid}")

        presentation[self.presentation_videos_endpoint] = videos = self.get_content(presentation['Id'], self.presentation_videos_endpoint)

        # getting content server for urls
        for video_file in videos:
            video_file['ContentServer'] = self.get_content_server(video_file['ContentServerId'])
            breakpoint()

        if not self.videos_urls_are_ok(presentation):
            presentation = {}
        else:
            for video_file in videos:
                encoding_settings_id = video_file['ContentEncodingSettingsId']
                video_file['ContentEncodingSettings'] = self.get_encoding_settings(encoding_settings_id)

            slides_endpoint = 'SlideDetailsContent' if mediasite_utils.has_slides_details(presentation) else 'SlideContent'
            presentation[slides_endpoint] = self.get_content(pid, slides_endpoint)
            presentation[slides_endpoint]['ContentServer'] = self.get_content_server(presentation['ContentServerId'], slide=True)
            if not self.slides_are_ok(presentation):
                return {}

            for content_endpoint in self.presentation_content_endpoints:
                presentation[content_endpoint] = self.get_content(pid, content_endpoint)

            presentation['PresentationAnalytics'] = self.mediasite_client.presentation.get_analytics(pid)
            presentation['Presenters'] = self.get_presenters(pid)
            presentation['Availability'] = self.mediasite_client.presentation.get_availability(pid)

            self.fetch_users(presentation)

        return presentation

    def get_content(self, *args):
        return self.mediasite_client.presentation.get_content(*args)

    def get_content_server(self, *args):
        return self.mediasite_client.content.get_content_server(*args)

    def videos_urls_are_ok(self, presentation):
        pid = presentation['Id']
        videos = presentation['OnDemandContent']

        videos_urls_ok, videos_urls_missing_count, videos_stream_types_count = mediasite_utils.check_videos_urls(videos, self.session)
        if not videos_urls_ok:
            logger.error(f'Failed to get a video file for presentation {pid}, moving to next one')
            self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['videos_missing'], collected=False))
        elif videos_urls_missing_count > 0:
            if videos_stream_types_count > 1:
                self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['composites_videos_missing'], collected=True))
                logger.error(f'At least one file is missing for composite video for presentation {pid}')
            else:
                self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['some_videos_missing'], collected=True))
                logger.warning(f'Some videos files not found for presentation {pid}')

        return videos_urls_ok

    def fetch_users(self, presentation):
        logger.debug(f"Fetching all users infos for presentation {presentation.get('Id')}.")
        for user_type in self.users_types_to_fetch:
            user = self._get_user(presentation.get(user_type, ''))
            if user:
                self.users.append(user)

    @lru_cache
    def _get_user(self, username):
        user = dict()

        if not username.startswith('Default Presenter'):
            logger.debug(f'Getting user info for {username}')

            user_result = self.mediasite_client.user.get_profile_by_username(username)
            if user_result:
                user = user_result

        return user

    def get_presenters(self, presentation_id):
        presenters = self.mediasite_client.presentation.get_presenters(presentation_id)
        if presenters:
            for i, presenter in enumerate(presenters):
                if presenter.get('DisplayName', '').startswith('Default Presenter'):
                    presenters.pop(i)
        return presenters

    def get_encoding_settings(self, settings_id):
        logger.debug(f'Getting encoding infos from api with settings id: {settings_id}')

        encoding_settings = self.mediasite_client.content.get_content_encoding_settings(settings_id)
        return encoding_settings

    def slides_are_ok(self, presentation):
        """
            Check slides urls, stream source, and timecodes

            return: if presentation has valid slides for migration
        """
        pid = presentation['Id']
        slides = self._get_slides(presentation)

        if slides:
            if not mediasite_utils.slides_urls_exists(presentation):
                slides_stream_type = slides.get('StreamType', '')
                if slides_stream_type == 'Slide':
                    logger.error(f'Slide from jpeg not found for presentation {pid}')
                    presentation_failure = Failed(pid, error=self.failed_presentations_errors['slides_jpeg_missing'], collected=False)
                    return False
                elif slides_stream_type.startswith('Video'):
                    logger.warning(f'Slide file created from video stream not found for presentation {pid}')
                    logger.warning(f'Detect slides will be lauched for presentation {pid}')
                    presentation_failure = Failed(pid, error=self.failed_presentations_errors['slides_video_missing'], collected=True)
                else:
                    logger.error(f'Slide file from unknown stream type [{slides_stream_type}] not found for presentation {pid}')
                    presentation_failure = Failed(pid, error=self.failed_presentations_errors['slides_unknown_stream_missing'], collected=False)
            else:
                for s_details in slides.get('SlideDetails', []):
                    if not mediasite_utils.timecode_is_correct(s_details['TimeMilliseconds'], presentation):
                        presentation_failure = Failed(pid, error=self.failed_presentations_errors['slides_timecodes'], collected=True)
        self.failed_presentations.append(presentation_failure)

        return presentation_failure.collected

    def _get_slides(self, presentation):
        slides = presentation.get('SlideDetailsContent')
        if not slides:
            # SlideDetailsContent returns a dict whereas SlideContent return a list (key 'value' in JSON response)
            slides = presentation.get('SlideContent')[0]
        if len(slides) < 1 or not self._slides_are_correct(slides):
            slides = {}

        return slides

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

    def get_timed_events(self, presentation):
        timed_events = []
        pid = presentation['Id']
        timed_events_result = self.mediasite_client.presentation.get_content(pid, resource_content='TimedEvents')
        for event in timed_events_result:
            event_data = dict()
            if event.get('Payload'):
                try:
                    event_xml = xml.parseString(event['Payload']).documentElement

                    event_position = event.get('Position', 0)
                    if mediasite_utils.timecode_is_correct(event_position, presentation):
                        event_data['Position'] = event_position
                        event_payload_tags = ['Number', 'Title']
                        for tag in event_payload_tags:
                            event_data[tag] = event_xml.getElementsByTagName(tag)[0].firstChild.nodeValue
                        timed_events.append(event_data)
                    else:
                        logger.warning(f'A timed event timecode is greater than the video duration for presentation {pid}')
                        self.failed_presentations.append(Failed(pid, error=self.failed_presentations_errors['timed_events_timecodes'], collected=True))
                        timed_events = []

                except Exception as e:
                    logger.debug(f'Failed to get timed event for presentation {pid}: {e}')

        return timed_events

    def download_all_slides(self):
        all_ok = True
        for folder in self.all_data:
            for p in folder.get('Presentations', []):
                self.nb_all_slides += mediasite_utils.get_slides_count(p)
                ok = self._download_presentation_slides(p)
                # if at least one is false, all is false
                all_ok *= ok

        if all_ok:
            logger.info(f'Sucessfully downloaded all slides: [{self.nb_all_slides}]')
        else:
            logger.error(f'Failed to download all slides from Mediasite: [{self.nb_all_downloaded_slides}] / [{self.nb_all_slides}]')
        return all_ok

    def _download_presentation_slides(self, presentation):
        ok = False
        if len(presentation.get('Slides', [])) <= 0:
            ok = True
        else:
            pid = presentation['Id']
            presentation_slides_urls = mediasite_utils.get_slides_urls(presentation)
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
