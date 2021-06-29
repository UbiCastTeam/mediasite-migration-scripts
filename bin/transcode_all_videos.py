#!/usr/bin/env python3
'''
This script allows to launch transcoding on all media that have been migrated
'''
import json
import time
import datetime

from mediasite_migration_scripts.ms_client.client import MediaServerClient
import mediasite_migration_scripts.utils.common as utils


def do_request(*args, **kwargs):
    global msc
    now = datetime.datetime.now()
    # reduce impact on users by only processing at night
    while now.hour >= 7:
        print('This is daytime, sleeping 1 min')
        time.sleep(60)
        now = datetime.datetime.now()

    before = time.time()
    response = msc.api(*args, **kwargs)
    took = time.time() - before
    took_ms = int(took * 1000)
    # be gentle by reducing the amount of requests when response time increases
    # for example, if request took 10s, we will sleep 50s
    if took_ms > 1000:
        sleep_for = int(took_ms / 200)
        print(f'Request on {args[0]} took {took_ms} ms, sleeping {sleep_for} s')
        time.sleep(sleep_for)
    return response


def transcode_all_videos():
    more = True
    start = ''
    index = 0
    succeeded = 0
    failed = 0
    non_transcodable = 0
    while more:
        print('Making request on latest (start=%s)' % start)
        response = do_request('latest/', params=dict(start=start, content='v', count=20, order_by='creation'))
        for item in response['items']:
            # only apply on content migrated using this project that is published
            if item['origin'] == 'mediatransfer' and item['validated']:
                index += 1
                oid = item['oid']
                resources = do_request('medias/resources-list/', method='get', params={'oid': oid})
                if '.m3u8' in str(resources):
                    print(f'Skipping {oid}: already transcoded')
                    continue
                try:
                    print('Launch transcoding on media %s: %s' % (index, oid))
                    params = json.dumps(dict(priority='low', behavior='delete'))
                    # behavior: action to do on existing resources
                    do_request('medias/task/', method='post', data=dict(
                        oid=item['oid'],
                        task='transcoding',
                        params=params,
                    ), timeout=300)
                except Exception as e:
                    if 'has no usable ressources' in str(e):
                        non_transcodable += 1
                    else:
                        print('WARNING: Failed to start transcoding task of video %s: %s' % (item['oid'], e))
                        failed += 1
                else:
                    succeeded += 1

        start = response['max_date']
        more = response['more']

    print('%s transcoding tasks started.' % succeeded)
    print('%s transcoding tasks failed to be started.' % failed)
    print('%s media have no resouces and cannot be transcoded.' % non_transcodable)
    print('Total media count: %s.' % (succeeded + failed + non_transcodable))


if __name__ == '__main__':
    conf = utils.read_json('config.json')
    global msc
    msc = MediaServerClient(utils.to_mediaserver_conf(conf))
    msc.check_server()

    transcode_all_videos()
