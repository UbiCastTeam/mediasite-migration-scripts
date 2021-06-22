#!/usr/bin/env python3
from pymediainfo import MediaInfo
import logging


def has_h264_video_track(url):
    tracks = get_tracks(url)
    for track in tracks:
        if track.track_type == 'Video':
            return track.format == 'AVC'


def get_tracks(url):
    tracks = []
    try:
        tracks = MediaInfo.parse(url, mediainfo_options={'Ssl_IgnoreSecurity': '1'}).tracks
    except RuntimeError:
        logging.error(f'Could not analyze {url}')
    return tracks
