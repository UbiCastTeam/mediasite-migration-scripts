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
