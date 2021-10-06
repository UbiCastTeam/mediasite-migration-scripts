#!/usr/bin/env python3
from pymediainfo import MediaInfo
import logging
import utils.http as http

logger = logging.getLogger(__name__)


def get_tracks(url):
    tracks = []
    try:
        tracks = MediaInfo.parse(url, mediainfo_options={'Ssl_IgnoreSecurity': '1'}).tracks
    except RuntimeError:
        logging.error(f'Could not analyze with mediainfo {url}')
    except FileNotFoundError:
        logger.error(f'File not found with mediainfo : {url}')
    except Exception as e:
        logger.error(f'Failed to analyze with mediainfo {url}: {e}')

    return tracks


def has_h264_video_track(url):
    tracks = get_tracks(url)
    for track in tracks:
        if track.track_type == 'Video':
            return track.format == 'AVC'


def get_duration_h(videos):
    # from milliseconds
    duration_h = 0
    duration_ms = int(videos[0].get('Length'))
    if duration_ms < 0:
        logger.error('Video duration provided is below zero')
    else:
        duration_h = duration_ms / (3600 * 1000)
    return round(duration_h, 2)


def parse_encoding_infos_with_mediainfo(video_url, session):
    logger.debug(f'Parsing encoding infos with MediaInfo for: {video_url}')
    encoding_infos = {}
    try:
        media_tracks = get_tracks(video_url)
        if not media_tracks:
            raise
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
            media_exists = http.url_exists(video_url, session)
            if not media_exists:
                logger.debug(f'Video {video_url} not reachable.')
        except Exception as e:
            logger.debug(e)
    return encoding_infos
