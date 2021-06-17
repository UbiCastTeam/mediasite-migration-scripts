#!/usr/bin/env python3
from mediasite_migration_scripts.utils.mediasite import MediasiteClient
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

    mediasite_client = MediasiteClient(config)

    json_result = mediasite_client.do_request(args.suffix)
    print(json.dumps(json_result, indent=4, sort_keys=True))
