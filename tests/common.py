import logging
from copy import copy

from mediasite_migration_scripts.mediatransfer import MediaTransfer
import mediasite_migration_scripts.utils.common as utils
import mediasite_migration_scripts.utils.mediaserver as mediaserver_utils
import tests.common as test_utils
from pathlib import Path

logger = logging.getLogger(__name__)
config = utils.read_json('config-test.json')
ms_utils = mediaserver_utils.MediaServerUtils(config)
ms_client = ms_utils.ms_client
TEST_CHANNEL_NAME = 'mediasite_e2e_target'
PARENT_TEST_CHANNEL_OID = 'c12619b455e75glxvuja'


def set_logger(*args, **kwargs):
    return utils.set_logger(*args, **kwargs)


def prepare_test_data_and_clients(config):
    try:
        mediasite_data = utils.read_json('tests/mediasite_test_data.json')

        samples_infos = {
            'mp4': {
                'oid': 'v12619b7260509beg5up',
                'url': 'https://beta.ubicast.net/resources/r12619b72604fpsvrzrflm70x1ad6z/media_720_0t4Q5Qjsx2.mp4'
            },
            'audio_only': {
                'oid': 'v1261b87a09e6oih5wdg',
                'url': 'https://beta.ubicast.net/resources/r1261b87a09e60ai635y67udj9g37x/grit_tapey_bass_bass_100bpm_dminor_bandlab_original.mp4'
            },
            'wmv': {
                'oid': 'v1261bdb8090ar6v1ttq',
                'url': 'https://beta.ubicast.net/resources/r1261bdb8090axavshifrvvo519n7c/sample_960x540_clean.wmv'
            }
        }

        for key in samples_infos.keys():
            result = ms_client.api(
                'download',
                method='get',
                params={'oid': samples_infos[key]['oid'],
                        'url': samples_infos[key]['url'], 'redirect': 'no'}
            )
            if not result.get('success'):
                logger.error(
                    'Failed to get urls for medias samples from Mediaserver')

            url_without_base = result.get('url').replace(config.get('mediaserver_url'), '')
            for folder in mediasite_data['Folders']:
                for presentation in folder['Presentations']:
                    for video in presentation['OnDemandContent']:
                        video_format = video['ContentMimeType']
                        if video_format == 'video/mp4' and key == 'mp4':
                            video['FileNameWithExtension'] = url_without_base
                        elif video_format == 'video/x-ms-wmv' and key == 'wmv':
                            video['FileNameWithExtension'] = url_without_base
                    if presentation['Title'] == 'Media with audio only' and key == 'audio_only':
                        presentation['OnDemandContent'][0]['FileNameWithExtension'] = url_without_base
        try:
            mediatransfer = MediaTransfer(config, mediasite_data)
        except Exception as e:
            logger.error(f'Failed to init MediaTransfer: {e}')
            raise AssertionError

        for media in mediatransfer.mediaserver_data:
            m_data = media.get('data', {})
            if m_data.get('video_type') == "composite_video":
                # m_data['composites_videos_urls'] = {
                #     'Video1': samples_infos['mp4']['url'], 'Video3': samples_infos['mp4']['url']}
                breakpoint()

        for media in mediatransfer.mediaserver_data:
            media_data = media['data']
            if media_data['title'] == 'Media with slides':
                mediatransfer.slides_folder = Path('tests/samples/slides')
                media_data['slides'] = test_utils.generate_slides_details()
                media_data['detect_slides'] = 'no'

        test_channel = create_test_channel()
        mediatransfer.root_channel = mediatransfer.get_channel(test_channel['oid'])

        return mediatransfer, ms_client
    except Exception as e:
        logger.error(f'Failed to prepare test data: {e}')
        exit(1)


def create_test_channel():
    test_channel = dict()
    test_channel_infos = {'title': TEST_CHANNEL_NAME, 'parent': PARENT_TEST_CHANNEL_OID}

    # channel with medias in it probably already exists if previous tests have been lauched,
    # we remove the channel to prevent duplicates as it's not well handled by MS
    result = ms_client.api('channels/get', method='get', params=test_channel_infos, ignore_404=True)
    if result is not None:
        rm_ok = ms_utils.remove_channel(oid=result['info']['oid'])
        if not rm_ok:
            logger.error(f"Failed to delete previous test channel {result.get('info').get('oid')} with his content")

    test_channel = ms_client.api('channels/add', method='post', data=test_channel_infos)

    return test_channel


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
