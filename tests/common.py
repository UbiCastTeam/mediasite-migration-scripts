import logging
import os
import json

from mediasite_migration_scripts.lib import utils


def set_logger(options, run_path):
    return utils.set_logger(options, run_path)

def make_test_data():

    data = []
    with open('data_debug.json') as f:
        data = json.load(f)

    new_data = []
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
