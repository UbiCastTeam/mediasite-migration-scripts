#!/usr/bin/env python3
# flake complains about the template
# flake8: noqa
import json
import sys

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



with open('config.json', 'r') as f:
    conf = json.load(f)

with open('redirections.json', 'r') as f:
    d = json.load(f)

from_root = '/'.join(conf['mediasite_api_url'].split('/')[:3])
nginx_server_name = from_root.replace('https://', '')
nginx_block = ''

for from_url, to_url in d.items():
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
