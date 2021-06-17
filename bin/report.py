#!/usr/bin/env python3
import csv
import json
import logging
from mediasite_migration_scripts.utils import common as utils
from mediasite_migration_scripts.ms_client.client import MediaServerClient
from mediasite_migration_scripts.utils.mediasite import MediasiteClient

argparser = utils.get_argparser()
argparser.add_argument(
    '--apply-changes',
    action='store_true',
    help='Perform changes (e.g. fix private status)',
)
argparser.add_argument(
    '--fix-private',
    action='store_true',
    help='Update MediaServer media published status to match the Private status in MediaSite',
)
args = argparser.parse_args()

utils.setup_logging(args.verbose)

config = utils.read_json('config.json')
mediasite_data = utils.read_json('mediasite_data.json')
redirections = utils.read_json('redirections.json')
redirections_copy = dict(redirections)

mediasite_client = MediasiteClient(config)
mediasite_cname = utils.get_mediasite_host(config['mediasite_api_url'])
mediasite_play_url_pattern = f'https://{mediasite_cname}/Site1/Play/'

ms_config = {
    'API_KEY': config['mediaserver_api_key'],
    'CLIENT_ID': 'mediasite-migration-client',
    'SERVER_URL': config['mediaserver_url'],
    'TIMEOUT': 60,
}
ms_client = MediaServerClient(local_conf=ms_config, setup_logging=False)


def get_mediaserver_media(oid):
    return ms_client.api('medias/get/', params={'oid': oid, 'path': 'yes'}, ignore_404=True)


def get_mediaserver_path(media):
    path_str = ''
    if media and media['success']:
        path = media['info']['path']
        for p in path:
            path_str += p['title'] + '/'
        return path_str + oid
    else:
        return


def set_media_private(oid, private_bool):
    logging.info(f'Setting {oid} to validated: {not private_bool}')
    r = ms_client.api('medias/edit/', method='post', data={'oid': oid, 'validated': 'no' if private_bool else 'yes'})
    if not r or not r['success']:
        logging.error(r)


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
        private = True
        if args.fix_private:
            presentation = mediasite_client.get_presentation(p_id)
            if presentation:
                private = presentation['Private']
            else:
                # presentation does not exist
                pass
        p_path = f['path'] + '/' + p_id
        mediasite_url = mediasite_play_url_pattern + p_id
        mediaserver_url = redirections.get(mediasite_url)
        if mediaserver_url:
            oid = mediaserver_url.split('/')[4]
            media = get_mediaserver_media(oid)
            if args.fix_private:
                is_private = not media['info']['validated']
                if private != is_private:
                    print(f'Video {oid} private status mismatch: {is_private} vs expected {private}')
                    if args.apply_changes:
                        set_media_private(oid, private)
                    else:
                        logging.info(f'Dry run: not setting {oid} published to {not private}')
            mediaserver_path = get_mediaserver_path(media)
            if not mediaserver_path:
                print(f'{oid} missing, it will be removed from the redirections')
                redirections_copy.pop(mediasite_url)
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

if redirections_copy != redirections:
    fixed_redirections_path = 'redirections_fixed.json'
    print(f'Saving fixed redirections into {fixed_redirections_path}')
    with open(fixed_redirections_path, 'w') as f:
        json.dump(redirections_copy, f, indent=2)

mediasite_client.close()
