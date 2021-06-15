# Mediasite Migration Scripts

Scripts to import video data from Mediasite to Ubicast Mediaserver

## Requirements

* make
* docker
* git
* git-lfs

## Usage

### Setup

First of all, you need to set up the connection with the Mediasite API and Mediaserver API.

- Clone the repository and submodules:

```
$ git clone https://github.com/UbiCastTeam/mediasite-migration-scripts
$ git submodule update --init
$ git-lfs install && git-lfs pull
```

You have to fill some credentials to config.json. Also, some parameters can be provided for migration.

- Create the config.json file

`$ cp config.json.example config.json`

- On config.json, put the parameters e.g. :

```
{
    "mediasite_api_url": "", # the API URL of your Mediasite server (e.g. https://my.mediasite.com/Site1/api/v1/)
    "mediasite_api_key": "", # API key generated in the Mediasite backoffice at /api/Docs/ApiKeyRegistration.aspx
    "mediasite_api_user": "", # Mediasite user name
    "mediasite_api_password":"", #  Mediasite user password
    "mediaserver_url":"", # API key generated in the Mediaserver backoffice at authentication/account-settings/
    "mediaserver_api_key": "", # Mediaserver URL (e.g. https://my.mediaserver.net/)
    "mediaserver_parent_channel": "", # the Mediaserver root channel oid where all the content will be migrate
    "whitelist": ["Migratietest_2021mrt16"], # folders you want to migrate from Mediasite
    "videos_formats_allowed": {   # video formats allowed
        "video/mp4": true,
        "video/x-ms-wmv": false
    },
    "external_data" : false # add Mediasite data in external data field on Mediaserver
}

```

## Running scripts
### Migrate

For migrating medias, considering the parameters you provided in config.json

`$ make migrate`

```
...
Connecting...
Getting presentations... (take a few minutes)
Uploading videos...
Uploading: [14 / 14] -- 100%
--------- Upload successful ---------

Uploaded 14 medias

```

### Analyze data
For collecting statistics about the videos included in the  Mediasite platform (video type, available file format, ...), and informations for migration.

`$ make analyze_data`

If it's the first time you run the script, it will require to collect data from Mediasite API.
```
$ make analyze_data
docker build -t mediasite -f Dockerfile .
Sending build context to Docker daemon  152.8MB
Step 1/7 : FROM debian:10
 ---> e7d08cddf791
Step 2/7 : RUN apt update && apt install -y         python3-coverage         python3-requests         make         flake8         python3-pip     && apt clean && rm -rf /var/lib/apt/lists/*
 ---> Using cache
 ...
No data to analyse.
Do you want to run import data ? [y/N] y
Connecting...
Requesting:  [10/595] -- 1.7 %

```

Collecting data will take a while (~ 5 minutes per 1000 media), and global stats will be printed on your terminal. Collected data are stored in **mediasite_data.json** in the root folder. If you keep the file, next time you run the script, collecting data will be skipped.

```
...
Found 595 folders
Number of presentations in folders: 2209
229 folders have no presentation inside 103 user folders
11% of videos without mp4 vs 90% with mp4
There's 11% of videos with no slide, 88% with slides, and 2% are compositions of multiple videos
Counting downloadable mp4s (among 1944 urls)
1815 downloadable mp4s, status codes: {'200': 1815, '404': 129}
```

### Import data only
If you want to only get the raw data, without analysis.

`$ make import_data`


## Arguments
You can pass arguments into the scripts, with the variable **ARGS**. Argument '--help' will provide you the list of arguments for a script.

```
$ make migrate ARGS="--help"
...
usage: migrate.py [-h] [-q] [-v] [--max-videos MAX_VIDEOS] [-cf] [-mf]

This script is used to import media from mediasite to mediaserver

optional arguments:
  -h, --help            show this help message and exit
  -q, --quiet           print less status messages to stdout.
  -v, --verbose         print all status messages to stdout.
  --max-videos MAX_VIDEOS
                        specify maximum of videos for upload.
  -cf, --config-file    add custom config file.
  -mf, --mediasite_file
                        add custom mediasite data file.
```

### Known limitations

* Docker does not support symlinked folders (e.g. download/ folder), prefer a bind mount over symlinks
