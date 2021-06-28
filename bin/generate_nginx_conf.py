#!/usr/bin/env python3
# flake complains about the template
# flake8: noqa
import json
import sys
from mediasite_migration_scripts.utils import common as utils


conf_template = '''
# nginx config file for preserving original presentation and catalog urls

server {
	listen 80;
	server_name %s;

	location /.well-known/acme-challenge {
		default_type "text/plain";
		root /var/www/letsencrypt;
	}
	location / {
		return 301 https://$host$request_uri;
	}
}

server {
	listen 443 ssl http2;
	server_name %s;

%s

	location / {
		return 404;
	}
}
'''

block_template = '\tlocation {from_url} {{ return 301 {to_url}; }}\n'

argparser = utils.get_argparser()

argparser.add_argument(
    '--additional-redirections-file',
    help='File containing additional URLs (one by line, each line should finish with presentation id like https://mymsite.com/Site1/MyMediasite/presentations/7b81b5a84d454d4e8cae691c7e6efe2sj8)'
)

args = argparser.parse_args()

conf = utils.read_json('config.json')
redirections = utils.read_json('redirections.json')

additional_redirections_count = 0
additional_redirections_dict = {}
if args.additional_redirections_file:
    with open(args.additional_redirections_file, 'r') as f:
        additional_redirections = f.read()
        for line in additional_redirections.split('\n'):
            pid = line.rstrip('/').split('/')[-1]
            if additional_redirections_dict.get(pid) is None:
                additional_redirections_dict[pid] = list()
            if line not in additional_redirections_dict[pid]:
                additional_redirections_dict[pid].append(line)
                additional_redirections_count += 1

    print(f'Found {additional_redirections_count} additional redirections for {len(additional_redirections_dict.keys())} presentations')

from_root = '/'.join(conf['mediasite_api_url'].split('/')[:3])
nginx_server_name = from_root.replace('https://', '')
nginx_block = ''

redirections_copy = dict(redirections)
for from_url, to_url in redirections.items():
    pid = from_url.split('/')[-1]
    if additional_redirections_dict.get(pid) is not None:
        add = additional_redirections_dict[pid]
        for r in add:
            redirections_copy[r] = to_url

for from_url, to_url in redirections_copy.items():
    if from_root not in from_url:
        print(f'Configuration mismatch, {from_root} not found')
        sys.exit(1)
    from_url = from_url.replace(from_root, '')
    nginx_block += block_template.format(**locals())

nginx_conf = conf_template % (nginx_server_name, nginx_server_name, nginx_block)

nginx_conf_path = f'{nginx_server_name}.conf'
with open(nginx_conf_path, 'w') as f:
    print(f'Writing nginx config into {nginx_conf_path}')
    f.write(nginx_conf)
