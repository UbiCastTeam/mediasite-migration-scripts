#!/usr/bin/env python3
import logging
import utils.http as http
from datetime import datetime
import xml.dom.minidom as xml


logger = logging.getLogger(__name__)


class MediasiteClient:
    def __init__(self, config):
        self.session = http.get_session(config['mediasite_api_user'],
                                        config['mediasite_api_password'],
                                        headers={'sfapikey': config['mediasite_api_key']})
        self.url_prefix = config['mediasite_api_url'].rstrip('/')

    def get_presentation(self, presentation_id):
        r = self.do_request(f"/Presentations('{presentation_id}')?$select=full")
        if r.get('odata.error'):
            return
        else:
            return r

    def do_request(self, suffix):
        url = f"{self.url_prefix}/{suffix.lstrip('/')}"
        return self.session.get(url).json()

    def close(self):
        self.session.close()


def timecode_is_correct(timecode, presentation):
    for video_file in presentation['OnDemandContent']:
        if int(timecode) > int(video_file['Length']):
            return False
    return True


def get_video_url(video_file, playback_ticket=str(), site=str()):
    video_file_url = str()
    # we skip smoothstreaming videos as it's not handled
    if not video_file['ContentMimeType'] == 'video/x-mp4-fragmented':
        content_server = video_file['ContentServer']
        distribution_url = content_server.get('DistributionUrl')
        if distribution_url:
            # distribution url pattern example: https://host.com/MediasiteDeliver/MP4Video/$$NAME$$?playbackTicket=$$PBT$$&site=$$SITE$$
            # playbackTicket is not handled yet, only works if file protection is deactivated, then playback ticket and site are optionnal
            url_mapping = {
                '$$NAME$$': video_file['FileNameWithExtension'],
                '$$PBT$$': playback_ticket,
                '$$SITE$$': site
            }
            video_file_url = distribution_url
            for param_name, param_value in url_mapping.items():
                video_file_url = video_file_url.replace(param_name, param_value)
    return video_file_url


def check_videos_urls(videos, session):
    """
        Check if at least one valid url exists for a video.
        In case of composites videos, all videos streams will be checked.

        return:
            video_urls_ok -> bool : a url exists for each video
            videos_urls_missing -> int : count of urls not reachables
            videos_stream_types_count -> int : count of videos streams types (> 1 if composites)
    """

    videos_found = list()
    videos_stream_types = set()
    videos_total_count = len(videos)

    for video_file in videos:
        # one video stream can have multiple files
        videos_stream_types.add(video_file['StreamType'])

        video_file_url = video_file.get('Url')
        if video_file_url is None:
            video_file_url = get_video_url(video_file)

        if video_file_url:
            video_file_found = http.url_exists(video_file_url, session)
            if video_file_found:
                videos_found.append(video_file)
            else:
                logger.warning(f'Video file not found: {video_file_url}')

    # all videos streams must have at least one video file with a valid url (in composites videos case, there's at least 2 videos streams)
    videos_stream_types_found = set()
    for stream_type in videos_stream_types:
        for v in videos_found:
            if stream_type == v['StreamType']:
                videos_stream_types_found.add(stream_type)
                break

    videos_urls_ok = (len(videos_stream_types) == len(videos_stream_types_found))
    videos_urls_missing_count = videos_total_count - len(videos_found)
    videos_stream_types_count = len(videos_stream_types)
    return videos_urls_ok, videos_urls_missing_count, videos_stream_types_count


def get_slides_count(slides):
    count = slides.get('Length', 0)
    return int(count)


def get_slides_urls(slides):
    slides_urls = list()

    if slides:
        pid = slides['ParentResourceId']
        logger.debug(f'Getting slides urls for presentation {pid}')

        content_server_id = slides['ContentServerId']
        content_server_url = slides['ContentServer']['Url']
        slides_base_url = f"{content_server_url}/{content_server_id}/Presentation/{pid}"
        for i in range(int(slides.get('Length', '0'))):
            # Transform string format (from C# to Python syntax) -> slides_{0:04}.jpg
            file_name = slides.get('FileNameWithExtension', '').replace('{0:D4}', f'{i+1:04}')
            file_url = f'{slides_base_url}/{file_name}'
            slides_urls.append(file_url)
    return slides_urls


def slides_urls_exists(slides, session):
    urls = get_slides_urls(slides)
    for u in urls:
        if not http.url_exists(u, session):
            return False
    return True


def has_slides_details(presentation):
    for stream_type in presentation.get('Streams'):
        if stream_type.get('StreamType') == 'Slide':
            return True
    return False


def is_composite(presentation):
    pid = presentation['Id']
    streams = presentation['Streams']
    video_count = 0
    for s in streams:
        if s.get('StreamType').startswith('Video'):
            video_count += 1
    if video_count > 2:
        logger.error(f'Unimplemented: presentation {pid} has more than 2 video sources')
    return video_count == 2


def get_preferred_file(files, allow_wmv=False):
    formats = ['video/mp4']
    if allow_wmv:
        formats.append('video/x-ms-wmv')
    for format_name in formats:
        for f in files:
            if f.get('format') == format_name and f.get('size_bytes') != 0:
                return f


def get_best_video_file(video, allow_wmv=False):
    files = video['files']
    video_file = {}
    max_width = 0

    preferred_file = get_preferred_file(files, allow_wmv)
    if preferred_file:
        info = preferred_file.get('encoding_infos', {})
        width = int(info.get('width', 0))
        if width >= max_width:
            video_file = preferred_file
    return video_file


def parse_mediasite_date(date_str):
    date_format = '%Y-%m-%dT%H:%M:%S'
    if '.' in date_str:
        # some media have msec included
        # 2016-12-07T13:07:27.58Z
        date_format += '.%f'

        date_str = date_str.replace('Z', '')
        ms = date_str.split('.')[1]
        # in datetime obj, ms are in 6 digits
        ms = '{ms:06}'.format(ms=int(ms))
        date_str = date_str.split('.')[0] + '.' + ms
    try:
        return datetime.strptime(date_str, date_format)
    except Exception as e:
        logger.error(f'Failed to parse mediasite date {date_str}: {e}')


def format_mediasite_date(data):
    date_format = '%Y-%m-%d %H:%M:%S'
    return data.strftime(date_format)


def get_most_distant_date(presentation):
    date_types = ['CreationDate', 'RecordDate']
    dates = list()

    for d_type in date_types:
        date_str = presentation.get(d_type)
        if date_str:
            date = parse_mediasite_date(date_str)
            dates.append(date)

    return format_mediasite_date(min(dates))


def get_age_days(date_str):
    days = (datetime.now() - parse_mediasite_date(date_str)).days
    return days


def parse_encoding_settings_xml(encoding_settings):
    """
        Parse encoding settings XML provided by MediaSite API

        returns:
            video codec, audio codec, width and height
    """
    encoding_infos = dict()
    try:
        serialized_settings = encoding_settings['SerializedSettings']
        settings_data = xml.parseString(serialized_settings).documentElement
        # Tag 'Settings' is a XML string to be parsed again...
        settings_node = settings_data.getElementsByTagName('Settings')[0]
        settings = xml.parseString(settings_node.firstChild.nodeValue)

        width = int(settings.getElementsByTagName('PresentationAspectX')[0].firstChild.nodeValue)
        height = int(settings.getElementsByTagName('PresentationAspectY')[0].firstChild.nodeValue)
        # sometimes resolution values given by the API are reversed, it's better to use MediaInfo in that case
        if width < height:
            logger.debug('Resolution values given by the API may be reversed...')
            return {}

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
        logger.debug(f'XML could not be parsed for video encoding settings: {e}')

    return encoding_infos


def parse_timed_events_xml(timed_events):
    parsed_timed_events = list()
    for event in timed_events:
        event_data = dict()
        if event.get('Payload'):
            try:
                event_xml = xml.parseString(event['Payload']).documentElement
                event_data['Position'] = event.get('Position', 0)
                event_payload_tags = ['Number', 'Title']
                for tag in event_payload_tags:
                    event_data[tag] = event_xml.getElementsByTagName(tag)[0].firstChild.nodeValue

                parsed_timed_events.append(event_data)
            except Exception as e:
                pid = timed_events['PresentationId']
                logger.debug(f'Failed to get timed event for presentation {pid}: {e}')

    return parsed_timed_events
