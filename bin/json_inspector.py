#!/usr/bin/env python3
import json
import argparse
import mediasite_migration_scripts.utils.mediasite as mediasite


parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument(
    '-i',
    '--input-file',
    type=str,
    help='Path to json file to analyze',
    default='mediasite_data.json',
)

parser.add_argument(
    '-s',
    '--search',
    type=str,
    help='Word or id to search for',
)

parser.add_argument(
    '--max-results',
    type=int,
    help='Maximum results to show, 0 to disable',
    default=10,
)

parser.add_argument(
    '--search-fields',
    type=str,
    help='Fields to search into (csv)',
    default='name,path,id'
)

args = parser.parse_args()
input_file = args.input_file
fields = args.search_fields.split(',')

folders = 0
presentations = 0
channels = 0
search_results_folders = list()
search_results_presentations = list()
search_results_channels = list()

with open(input_file, 'r') as f:
    print(f'Loading {input_file}')
    d = json.load(f)
    s = args.search
    if s:
        print(f'Searching for {s} in fields {fields}')
    for f in d:
        folders += 1
        presentations += len(f.get('presentations', []))
        channels += len(f.get('channels', []))

        if s:
            # hide content that is too verbose
            f_copy = dict(f)
            f_copy['presentations'] = [f'{len(f["presentations"])} presentations (hidden)']

            for field in fields:
                val = f.get('field')
                if val and s in val:
                    if f_copy not in search_results_folders:
                        search_results_folders.append(f_copy)
                        print(f'Found term "{s}" in field "{field}" of folder {f_copy["id"]}')
                for p in f.get('presentations', []):
                    p_copy = dict(p)
                    slides_count = mediasite.get_slides_count(p)
                    p_copy['slides'] = [f'{slides_count} slides (hidden)']
                    if s in p.get(field, ''):
                        if p_copy not in search_results_presentations:
                            search_results_presentations.append(p_copy)
                            print(f'Found term "{s}" in field "{field}" of presentation {p_copy["id"]}')
                for c in f.get('channels', []):
                    if s in c.get(field, ''):
                        if c not in search_results_channels:
                            search_results_channels.append(c)
                            print(f'Found term "{s}" in field "{field}" of channel {c["id"]}')


def print_short(items, max_items=10):
    if max_items == 0:
        max_items = float("inf")
    if len(items) == 0:
        pass
    elif 0 < len(items) < max_items:
        print(json.dumps(items, indent=2))
    else:
        print(json.dumps(items[:max_items], indent=2))
        print(f'Truncated to the first {max_items} items')
    print(f'Finished displaying {len(items)} results')


results = [
    ['folders', search_results_folders],
    ['presentations', search_results_presentations],
    ['channels', search_results_channels],
]

print(f'Total: {folders} folders, {presentations} presentations, {channels} channels')
if args.search:
    for name, result in results:
        print(f'Found {len(result)} in {name} search results')
        print_short(result, args.max_results)
