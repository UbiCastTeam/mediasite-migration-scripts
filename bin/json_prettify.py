#!/usr/bin/env python3
# create a human readable version of the large files
# the output name prefixes the input name with pretty_
import json
import sys

try:
    fin = sys.argv[1]
except IndexError:
    print('Provide json file as input argument')
    sys.exit(1)

fout = 'pretty_' + fin

with open(fin, 'r') as f:
    print(f'Reading {fin}')
    d = json.load(f)
    with open(fout, 'w') as o:
        print(f'Writing {fout}')
        json.dump(d, o, indent=4)
print('Done')
