#!/usr/bin/env python3
import requests


class MediasiteClient:
    def __init__(self, config):
        self.headers = {
            'sfapikey': config['mediasite_api_key'],
        }
        self.auth = requests.auth.HTTPBasicAuth(config['mediasite_api_user'], config['mediasite_api_password'])
        self.url_prefix = config['mediasite_api_url'].rstrip('/')
        self.session = requests.Session()

    def get_presentation(self, presentation_id):
        r = self.do_request(f"/Presentations('{presentation_id}')?$select=full")
        if r.get('odata.error'):
            return
        else:
            return r

    def do_request(self, suffix):
        url = f"{self.url_prefix}/{suffix.lstrip('/')}"
        return self.session.get(url, headers=self.headers, auth=self.auth).json()

    def close(self):
        self.session.close()


def get_slides_count(presentation):
    count = 0
    if presentation.get('slides'):
        count = len(presentation['slides'].get('urls', []))
    return count


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
