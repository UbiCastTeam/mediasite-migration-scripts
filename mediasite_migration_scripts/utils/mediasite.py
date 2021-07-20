#!/usr/bin/env python3
import logging
import utils.http as http
from datetime import datetime
from pathlib import Path

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


def get_video_url(video_file):
    video_file_url = str()

    content_server = video_file['ContentServer']
    distribution_url = content_server.get('DistributionUrl')
    if distribution_url:
        # popping odata query params, we just need the route
        base_url_splitted = distribution_url.split('/')
        base_url_splitted.pop()
        base_url = '/'.join(base_url_splitted)
    video_file_name = video_file['FileNameWithExtension']
    video_file_url = (base_url + video_file_name) if video_file_name and base_url else None

    return video_file_url


def valid_videos_urls_exists(videos, session):
    exists = True
    videos_found = list()
    videos_stream_types = set()

    for video_file in videos:
        videos_stream_types.update(video_file['StreamType'])

        video_file_url = get_video_url(video_file)
        video_file_found = http.url_exists(video_file_url, session)
        if not video_file_found:
            logger.warning(f'Video file not found: {video_file_url}')
            videos_found.append(video_file)

    # check if all streams types have a video with a valid url (in composites videos case, there's at least 2 videos streams)
    for stream_type in videos_stream_types:
        stream_type_found = False
        for v in videos_found:
            if stream_type == v['StreamType']:
                stream_type_found = True
                break
            if not stream_type_found:
                exists = False

    return exists


def get_slides_count(presentation_infos):
    count = presentation_infos.get('Slides', {}).get('Length', 0)
    return int(count)


def get_slides_urls(presentation_infos):
    slides_urls = list()

    pid = presentation_infos['Id']
    logger.debug(f'Getting slides urls for presentation {pid}')

    slides = presentation_infos.get('Slides')
    if slides:
        content_server_id = slides['ContentServerId']
        content_server_url = slides['ContentServer']['Url']
        slides_base_url = f"{content_server_url}/{content_server_id}/Presentation/{pid}"

        for i in range(int(slides.get('Length', '0'))):
            # Transform string format (from C# to Python syntax) -> slides_{0:04}.jpg
            file_name = slides.get('FileNameWithExtension', '').replace('{0:D4}', f'{i+1:04}')
            file_url = f'{slides_base_url}/{file_name}'
            slides_urls.append(file_url)

    return slides_urls


def slides_urls_exists(presentation_infos, session):
    urls = get_slides_urls(presentation_infos)
    for u in urls:
        if not http.url_exists(u, session):
            return False
    return True


def get_duration_h(videos):
    return videos[0]['files'][0].get('duration_ms', 0) / (3600 * 1000)


def is_composite(presentation):
    videos = presentation['videos']
    video_count = len(videos)
    if video_count > 2:
        raise Exception('Unimplemented: more than 2 video sources')
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
    #2010-05-26T07:16:57Z
    if '.' in date_str:
        # some media have msec included
        #2016-12-07T13:07:27.58Z
        date_str = date_str.split('.')[0] + 'Z'
    if not date_str.endswith('Z'):
        date_str += 'Z'
    return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')


def format_mediasite_date(date):
    return date.strftime('%Y-%m-%dT%H:%M:%SZ')


def get_most_distant_date(presentation_infos):
    most_distant_date_str = str()
    date_types = ['CreationDate', 'RecordDate']
    dates = list()

    for d_type in date_types:
        date_str = presentation_infos.get(d_type)
        if date_str:
            date = parse_mediasite_date(date_str)
            dates.append(date)
    most_distant_date = min(dates)
    most_distant_date_str = format_mediasite_date(most_distant_date)

    return most_distant_date_str


def strip_milliseconds(self, date):
    return date[:-1].split('.')[0]


def get_age_days(date_str):
    days = (datetime.now() - parse_mediasite_date(date_str)).days
    return days
