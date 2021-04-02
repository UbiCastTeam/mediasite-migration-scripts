# Mediasite Migration Scripts

Scripts to import video data from Mediasite to Ubicast Mediaserver

## Requirements

* make
* docker

## Usage

### Setup

First of all, you need to set up the connection with the Mediasite API.

- Clone the repository and submodules:

```
$ git clone https://github.com/UbiCastTeam/mediasite-migration-scripts
$ git submodule update --init
```

- Create the .env file

`$ cp .env.dist .env`

- Fill it with your credentials:

```
MEDIASITE_API_URL = the API URL of your Mediasite server (e.g. https://my.mediasite.com/Site1/api/v1/)
MEDIASITE_API_USER = Mediasite user name
MEDIASITE_API_PASSWORD = Mediasite user password
MEDIASITE_API_KEY = API key generated in the Mediasite backoffice at /api/Docs/ApiKeyRegistration.aspx

MEDIASERVER_API_KEY= API key generated in the Mediaserver backoffice at authentication/account-settings/
MEDIASERVER_URL= Mediaserver URL
```
### Config
Some parameters can be provided for migration.

- Create the config.json file

`$ cp config.json.example config.json`

- On config.json, put the parameters e.g. :

```
{
    "whitelist": ["Migratietest_2021mrt16"], # folders you want to migrate from Mediasite
    "videos_formats_allowed": {   # video formats allowed
        "video/mp4": true,
        "video/x-ms-wmv": false
    },
    "mediaserver_parent_channel": "c1261953feb82i5nhpis" # the Mediaserve root channel of all the content you migrate from Mediasite
}
```

## Running scripts
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

Collecting data will take a while (~ 5 minutes per 1000 media), and global stats will be printed on your terminal. Collected data are stored in **data.json** in the root folder. If you keep the file, next time you run the script, collecting data will be skipped.

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
If you do not want to analyze your, but only get the raw data. 

`$ make import_data`

### Migrate
For migrating medias, considering the parameters you provided in config.json

```
$ make migrate
...
Connecting...
Getting presentations... (take a few minutes)
Uploading videos...
Uploading: [14 / 14] -- 100%                      
--------- Upload successful ---------
 
Uploaded 14 medias

```

## Arguments
You can pass arguments into the scripts, with the variable **ARGS**.

```
$ make analyze_data ARGS="--verbose"
```

 
