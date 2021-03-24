import json
import os
from datetime import datetime


from mediasite_migration_scripts.lib import utils
from mediasite_migration_scripts.mediatransfer import MediaTransfer

MEDIASITE_DATA_FILE = 'tests/mediasite_data_test.json'
MEDIASERVER_DATA_FILE = 'tests/mediaserver_data_test.json'


def set_logger(*args, **kwargs):
    return utils.set_logger(*args, **kwargs)


def set_test_data():
    new_data = list()
    file = MEDIASITE_DATA_FILE

    if os.path.exists(file):
        with open(file) as f:
            new_data = json.load(f)
    else:
        data = list()
        with open('mediasite_data_debug.json') as f:
            data = json.load(f)

        i = 0
        for folder in data:
            presentations = folder['presentations']
            folder['presentations'] = []
            j = 0
            for p in presentations:
                if p['slides']:
                    slides_urls = p['slides']['urls']
                    p['slides']['urls'] = []
                    k = 0
                    for u in slides_urls:
                        p['slides']['urls'].append(u)
                        k += 1
                        if k >= 2:
                            break

                    slides_details = p['slides']['details']
                    if not slides_details:
                        slides_details = []
                    p['slides']['details'] = []
                    x = 0
                    for d in slides_details:
                        p['slides']['details'].append(d)
                        x += 1
                        if x >= 2:
                            break

                folder['presentations'].append(p)
                j += 1
                if j >= 2:
                    break

            new_data.append(folder)

            i += 1
            if i >= 2:
                break

    return new_data


def create_test_channel():
    test_channel = dict()
    test_channel_name = 'test-{dt.month}/{dt.day}/{dt.year}-{dt.hour}:{dt.minute}:{dt.second}'.format(dt=datetime.now())

    mediatransfer = MediaTransfer()
    ms_client = mediatransfer.ms_client
    test_channel = ms_client.api('channels/add', method='post', data={'title': test_channel_name, 'parent': mediatransfer.root_channel.get('oid')})
    ms_client.session.close()

    return test_channel