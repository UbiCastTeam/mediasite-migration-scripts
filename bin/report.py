#!/usr/bin/env python3
import csv
from mediasite_migration_scripts.utils import common as utils
from mediasite_migration_scripts.ms_client.client import MediaServerClient


config = utils.read_json('config.json')
mediasite_data = utils.read_json('mediasite_data.json')
redirections = utils.read_json('redirections.json')

mediasite_cname = utils.get_mediasite_host(config['mediasite_api_url'])
mediasite_play_url_pattern = f'https://{mediasite_cname}/Site1/Play/'


ms_config = {
    'API_KEY': config['mediaserver_api_key'],
    'CLIENT_ID': 'mediasite-migration-client',
    'SERVER_URL': config['mediaserver_url'],
    'TIMEOUT': 60,
}

ms_client = MediaServerClient(local_conf=ms_config, setup_logging=False)


def get_mediaserver_path(oid):
    r = ms_client.api('medias/get/', params={'oid': oid, 'path': 'yes'})
    path_str = ''
    if r['success']:
        path = r['info']['path']
        for p in path:
            path_str += p['title'] + '/'
    return path_str + oid


rows = list()
folders_to_process = list()
total_presentations = processed_presentations = skipped_presentations = 0
print('Filtering folders')
for folder in mediasite_data:
    if utils.is_folder_to_add(folder['path'], config):
        folders_to_process.append(folder)
        total_presentations += len(folder['presentations'])

print(f'Verifying {len(folders_to_process)} folders and {total_presentations} presentations')
for f in folders_to_process:
    for p in f['presentations']:
        oid = mediaserver_path = 'SKIPPED'
        print(utils.get_progress_string(processed_presentations, total_presentations), end='\r')
        processed_presentations += 1
        p_id = p['id']
        p_path = f['path'] + '/' + p_id
        mediasite_url = mediasite_play_url_pattern + p_id
        mediaserver_url = redirections.get(mediasite_url)
        if mediaserver_url:
            oid = mediaserver_url.split('/')[4]
            mediaserver_path = get_mediaserver_path(oid)
        else:
            mediaserver_url = 'SKIPPED'
            skipped_presentations += 1

        rows.append({
            'mediasite_path': p_path,
            'mediaserver_path': mediaserver_path,
            'mediasite_url': mediasite_url,
            'mediaserver_url': mediaserver_url
        })

print()
print(f'{skipped_presentations}/{total_presentations} presentations have not been migrated')
print('Writing csv')
with open('report.csv', 'w', newline='') as csvfile:
    fieldnames = ['mediasite_path', 'mediaserver_path', 'mediasite_url', 'mediaserver_url']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
