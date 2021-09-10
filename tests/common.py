import logging
from copy import copy

import mediasite_migration_scripts.utils.common as utils


logger = logging.getLogger(__name__)
config = utils.read_json('config-test.json')


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


def filter_for_tests(data):
    filtered_data = dict()
    for f_index, folder in enumerate(data['Folders']):
        for p_index, presentation in enumerate(folder['Presentations']):
            if presentation.get('TimedEvents'):
                filtered_data['Folders'] = [data['Folders'][f_index]]
                filtered_data['Folders'][0]['Presentations'][p_index]['TimedEvents'] = generate_timed_events()
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
