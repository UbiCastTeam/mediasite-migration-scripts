#!/usr/bin/env python3
import requests
from requests.auth import HTTPBasicAuth
import json
import argparse


if __name__ == '__main__':

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        '--config_file',
        type=str,
        help='Path to file containing presentation ids (one per line)',
        default='config.json'
    )

    parser.add_argument(
        'suffix',
        type=str,
        help="API suffix between quotes, like \"/Presentations('123456789436516516814681')/TimedEvents\"",
    )

    args = parser.parse_args()

    with open('config.json', 'r') as f:
        config = json.load(f)

    headers = {
        'sfapikey': config['mediasite_api_key'],
    }

    url = f"{config['mediasite_api_url'].rstrip('/')}/{args.suffix.lstrip('/')}"
    print(url)

    r = requests.get(url, auth=HTTPBasicAuth(config['mediasite_api_user'], config['mediasite_api_password']), headers=headers)
    json_result = r.json()
    print(json.dumps(json_result, indent=4, sort_keys=True))
