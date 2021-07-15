#!/usr/bin/env python3
from xml.dom.minidom import parse
import utils.http as http
from datetime import datetime


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


def get_slides_count(presentation_infos):
    count = presentation_infos.get('Slides', {}).get('Length', 0)
    return int(count)


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
