#!/usr/bin/env python3
'''
This script allows to launch transcoding on all media that have been migrated
'''
import json

from mediasite_migration_scripts.ms_client.client import MediaServerClient
import mediasite_migration_scripts.utils.common as utils


def transcode_all_videos(msc):
    more = True
    start = ''
    index = 0
    succeeded = 0
    failed = 0
    non_transcodable = 0
    while more:
        print('//// Making request on latest (start=%s)' % start)
        response = msc.api('latest/', params=dict(start=start, content='v', count=20, order_by='creation'))
        for item in response['items']:
            # only apply on content migrated using this project that is published
            if item['origin'] == 'mediatransfer' and item['validated']:
                index += 1
                oid = item['oid']
                print('// Media %s: %s' % (index, oid))
                resources = msc.api('medias/resources-list/', method='get', params={'oid': oid})
                if '.m3u8' in str(resources):
                    print(f'Skipping {oid}: already transcoded')
                    continue
                try:
                    params = json.dumps(dict(priority='low', behavior='delete'))
                    # behavior: action to do on existing resources
                    msc.api('medias/task/', method='post', data=dict(
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
    msc = MediaServerClient(utils.to_mediaserver_conf(conf))
    msc.check_server()

    transcode_all_videos(msc)
