import logging

import mediasite_migration_scripts.utils.mediasite as mediasite_utils
import mediasite_migration_scripts.utils.media as media

logger = logging.getLogger(__name__)


def order_and_filter_videos(presentation):
    pid = presentation['Id']
    logger.debug(f'Gathering video info for presentation : {pid}')

    ordered_videos = list()
    videos = presentation['OnDemandContent']
    ordered_videos = order_by_stream_type(videos)
    return ordered_videos


def order_by_stream_type(videos):
    videos_by_stream = list()
    videos_streams_types = list()

    for file in videos:
        file_stream_type = file['StreamType']
        if file_stream_type not in videos_streams_types and file_stream_type.startswith('Video'):
            videos_streams_types.append(file_stream_type)

        file_url = mediasite_utils.get_video_url(file)
        if file_url:
            file = {
                'url': file_url,
                'format': file.get('ContentMimeType'),
                'size_bytes': int(file.get('FileLength')),
                'encoding_infos': mediasite_utils.parse_encoding_settings_xml(file.get('ContentEncodingSettings', ''))
                or media.parse_encoding_infos_with_mediainfo(file_url)
            }

            video_index = get_video_index_by_stream(file_stream_type, videos_by_stream)
            if video_index is None:
                videos_by_stream.append({'stream_type': file_stream_type,
                                         'files': [file]})
            else:
                videos_by_stream[video_index]['files'].append(file)

    return videos_by_stream


def get_video_index_by_stream(stream_type, videos_list):
    for index, video in enumerate(videos_list):
        if stream_type == video.get('stream_type'):
            return index
    return None


def to_chapters(timed_events):
    chapters = []
    try:
        chapters = mediasite_utils.parse_timed_events_xml(timed_events)
    except Exception as e:
        logger.warning(f'Non valid chapter: {e}')

    return chapters
