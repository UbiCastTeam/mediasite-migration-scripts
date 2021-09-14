import logging
from copy import copy

import utils.common as utils


logger = logging.getLogger(__name__)
config = utils.read_json('config-test.json')


class DataFilter():
    def __init__(self, filter_fields):
        self.filter_fields = filter_fields

    def filter_data(self, data):
        logger.info('Filtering data')
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
                        field_value = self._filter_fields(data.get(key), val)
                        if field_value is not None:
                            filtered_data[key] = field_value
                elif isinstance(field, str):
                    field_value = data.get(field)
                    if field_value is not None:
                        filtered_data[field] = field_value

        return filtered_data


def set_logger(*args, **kwargs):
    return utils.set_logger(*args, **kwargs)


def anonymize_data(data):
    fields_to_anonymize = [
        'Title',
        'Name',
        'RootOwner',
        'Creator',
        'PrimaryPresenter',
        'DisplayName',
        'Email',
        'ParentFolderName',
        'FirstName',
        'LastName'
    ]
    user_fields_to_anonymize = ['Owner', 'UserName']

    anon_data = copy(data)
    if isinstance(anon_data, dict):
        for key, val in anon_data.items():
            if isinstance(val, dict) or isinstance(val, list):
                anon_data[key] = anonymize_data(val)
            elif isinstance(val, str):
                if 'http' and '://' in val:
                    if key == 'DistributionUrl':
                        anon_data[key] = config.get('mediaserver_url') + '$$NAME$$'
                    else:
                        anon_data[key] = 'https://anon.com/fake'
                elif ('@' in val and '.' in val) or (key in user_fields_to_anonymize):
                    anon_data[key] = 'anon@mail.com'
                elif key in fields_to_anonymize:
                    anon_data[key] = f'anon {key}'

    elif isinstance(anon_data, list):
        for i, item in enumerate(anon_data):
            anon_data[i] = anonymize_data(item)

    return anon_data


def to_small_data(data):
    filtered_data = dict()

    folders = data['Folders'][:2]
    if len(folders[0]['Presentations']) > 6:
        folders[0]['Presentations'] = folders[0]['Presentations'][:6]
    filtered_data['Folders'] = folders

    for i in range(2):
        filtered_data['Folders'][0]['Presentations'][i]['TimedEvents'] = generate_timed_events()

    users = data.get('UserProfiles')
    if users:
        filtered_data['UserProfiles'] = users[:1]

    return filtered_data


def generate_timed_events():
    timed_events = list()
    total = 3
    for i in range(total):
        timed_events.append({
            'Position': i * 1500,
            'Payload': f'<ChapterEntry ><Number>{i}</Number><Time>0</Time><Title>Chapter {i}</Title></ChapterEntry>'
        })
    return timed_events


def generate_slides_details():
    slides_details = dict()
    slides_details['Length'] = slides_count = 3
    slides_details['SlideDetails'] = list()
    for i in range(slides_count):
        slides_details['SlideDetails'].append({
            'Title': f'Slide {i + 1}',
            'TimeMilliseconds': 1500 * i,
            'Content': f'Content {i + 1}'
        })
    return slides_details
