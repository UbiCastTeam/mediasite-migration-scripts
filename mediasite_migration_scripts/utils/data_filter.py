import logging
import utils.mediasite as mediasite_utils

logger = logging.getLogger(__name__)


class DataFilter():
    def __init__(self, filter_fields):
        self.filter_fields = filter_fields

    def filter_data(self, data):
        self.data = data
        self.filtered_data = self._filter_data(data, self.filter_fields)
        return self.filtered_data

    def _filter_data(self, data, filter_fields):
        filtered_data = dict()
        for key, val in data.items():
            if key in filter_fields.keys():
                filtered_data[key] = self._filter_fields(val, filter_fields[key])
        return filtered_data

    def _filter_fields(self, data, filter_fields):
        filtered_data = None
        if isinstance(data, list):
            filtered_data = list()
            for item in data:
                filtered_data.append(self._filter_fields(item, filter_fields))
        elif isinstance(data, dict):
            filtered_data = dict()
            for field in filter_fields:
                if isinstance(field, dict):
                    for key, val in field.items():
                        filtered_data[key] = self._filter_fields(data.get(key), val)
                elif isinstance(field, str):
                    filtered_data[field] = data.get(field)

        return filtered_data


def order_and_filter_videos(presentation_infos):
    pid = presentation_infos['Id']
    logger.debug(f'Gathering video info for presentation : {pid}')

    videos_infos = list()
    videos = presentation_infos['OnDemandContent']
    videos_infos, videos_not_found_count, videos_streams_types = order_by_stream_type(videos)

    return videos_infos


def order_by_stream_type(videos):
    videos_list = list()
    videos_streams_types = list()
    videos_not_found_count = int()

    for file in videos:
        file_stream_type = file['StreamType']
        if file_stream_type not in videos_streams_types and file_stream_type.startswith('Video'):
            videos_streams_types.append(file_stream_type)

        file_url = mediasite_utils.get_video_url(file)
        if file_url:
            if not file.get('encoding_infos'):
                logger.debug(f"Video encoding infos not found in API for presentation: {file['ParentResourceId']}")

            stream_index = get_video_stream_index(file_stream_type, videos_list)
            if stream_index is None:
                videos_list.append({'stream_type': file_stream_type,
                                    'files': [file]})
            else:
                videos_list[stream_index].append(file)

    return videos_list, videos_not_found_count, videos_streams_types


def get_video_stream_index(stream_type, videos_list):
    for index, video in enumerate(videos_list):
        if stream_type == video.get('stream_type'):
            return index
    return None
