# Mediasite Migration Scripts

Scripts to import video data from Mediasite to Ubicast Mediaserver

## Requirements

* make
* docker

## Usage

### Videos statistics

For collecting statistics about the videos included in the  Mediasite platform (video type, available file format, ...):

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
```

- Run the script :

```
$ make stats
docker build -t mediasite -f Dockerfile .
Sending build context to Docker daemon    598kB
Step 1/5 : FROM debian:10
 ---> c2c03a296d23
Step 2/5 : RUN apt update && apt install -y         python3-coverage         python3-requests         make         flake8         python3-pip     && apt clean && rm -rf /var/lib/apt/lists/*
 ---> Using cache
...
{'video/mp4': '91%', 'video/x-ms-wmv': '8%', 'video/x-mp4-fragmented': '1%'}
```

Script will take a while (~ 5 minutes minutes per 1000 media), and global stats will be printed on your terminal. Also, some of the collected metadata are stored in json files in the root folder (presentations_folders.json and composition_videos.json).
