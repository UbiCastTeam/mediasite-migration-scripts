import json

file = 'tests/mediasite_data_test.json'
with open(file) as f:
    data = json.load(f)

for folder in data:
    for p in folder['presentations']:
        if p.get('has_slides_details'):
            ms = 0
            for s_details in p['slides']['details']:
                s_details['TimeMilliseconds'] = ms
                ms += 1

with open(file, 'w') as f:
    json.dump(data, f)

