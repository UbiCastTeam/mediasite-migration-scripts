#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import json
from datetime import datetime
from decouple import config
import argparse
from argparse import RawTextHelpFormatter

from assets.mediasite import controller as mediasite_controller


if __name__ == "__main__":
    # ------------------------------- Setup & Config

    # args
    def usage(message=''):
        return 'This script is used to import medias from mediasite platform'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=RawTextHelpFormatter)
        parser.add_argument('-i', '--info', action='store_true',
                            dest='info', default=False,
                            help='print more status messages to stdout.')
        parser.add_argument('-v', '--verbose', action='store_true',
                            dest='verbose', default=False,
                            help='print all status messages to stdout.')
        parser.add_argument('-d', '--dry-run', action='store_true',
                            dest='dryrun', default=False,
                            help='not really import medias.')
        parser.add_argument('-s', '--stats', action='store_true',
                            dest='stats', default=False,
                            help='displays the proportion of video formats in mediasite (mp4 / wmv / ism)')
        return parser.parse_args()

    options = manage_opts()

    #gather our runpath for future use with various files
    run_path = os.path.dirname(os.path.realpath(__file__))

    #logger params
    current_datetime_string = '{dt.month}-{dt.day}-{dt.year}'.format(dt=datetime.now())
    logging_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging_datefmt = '%m/%d/%Y - %I:%M:%S %p'
    formatter = logging.Formatter(logging_format, datefmt=logging_datefmt)

    logger = logging.getLogger()
    if options.verbose:
        level = logging.DEBUG
    elif options.info:
        level = logging.INFO
    else:
        level = logging.WARNING
    logger.setLevel(level)

    #logger for console
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    #logger for log file
    logs_folder = f'{run_path}/logs/'
    os.makedirs(logs_folder, exist_ok=True)
    logfile_path = os.path.join(logs_folder, f'test_{current_datetime_string}.log')
    logfile = logging.FileHandler(logfile_path)
    logfile.setFormatter(formatter)

    logger.addHandler(logfile)
    logger.addHandler(console)

    #open config file with configuration info
    try:
        config_data = {
            "mediasite_base_url": config('MEDIASITE_API_URL'),
            "mediasite_api_secret": config('MEDIASITE_API_KEY'),
            "mediasite_api_user": config('MEDIASITE_API_USER'),
            "mediasite_api_pass": config('MEDIASITE_API_PASSWORD')
        }
    except KeyError:
        logging.error('No environment file')

    # ------------------------------- Functions
    # globals
    mediasite = mediasite_controller.controller(config_data)
    presentations_length = mediasite.presentation.get_number_of_presentations()
    api_url = config_data['mediasite_base_url']
    splited_url = api_url.split('/')
    host_url = splited_url[0] + '//' + splited_url[2]
    iterations = 0

    def get_videos_infos(presentations_folders, stats=False):
        logging.info("Gathering all videos infos")

        i = 0
        videos_infos = []
        for folder in presentations_folders:
            print('Requesting: ', f'{i} / {len(folders)} folders', end='\r', flush=True)
            for presentation in folder['presentations']:
                video = mediasite.presentation.get_presentation_content(presentation['id'], 'OnDemandContent')
                videos_infos.append({
                    'presentation_id': presentation['id'],
                    'presentation_title': presentation['title'],
                    'folder': find_folder_path(folder['id'], presentations_folders),
                    'videos': get_video_detail(video)
                })
            i += 1
        return videos_infos

        global presentations_length
        if stats:
            video_count = {}
            for video in videos_infos:
                for video_format in video['video_formats']:
                    if video_format in video_count:
                        video_count[video_format] += 1
                    else:
                        video_count[video_format] = 1
            stats = {}
            for video_format, count in video_count.items():
                stats[video_format] = str(round(count / presentations_length * 100)) + '%'

            print(stats)

    def get_video_detail(video):
        global host_url
        videos_dir = f'{host_url}/MediasiteDeliver/MP4Video/'
        video_list = []
        if video:
            for file in video['value']:
                file_name = file['FileNameWithExtension']
                video_url = os.path.join(videos_dir, file_name) if (file_name) else None
                file_infos = {'format': file['ContentMimeType'], 'url': video_url}

                stream = file['StreamType']
                in_list = False
                for v in video_list:
                    if stream == v.get('stream_type'):
                        in_list = True
                        v['files'].append(file_infos)
                if not in_list:
                    video_list.append({'stream_type': stream,
                                       'files': [file_infos]})
        return video_list

    def compute_videos_stats(videos_infos):
        count = {}
        for video in videos_infos:
            video_format = find_best_format(video)
            if video_format in count:
                count[video_format] += 1
            else:
                count[video_format] = 1

        stats = {}
        for v_format, v_count in count.items():
            stats[v_format] = str(round((v_count / len(videos_infos)) * 100)) + '%'
        return stats

    def find_best_format(video):
        formats_priority = ['video/mp4', 'video/x-ms-wmv', 'video/x-mp4-fragmented']
        for priority in formats_priority:
            for file in video['videos'][0]['files']:
                if file['format'] == priority:
                    return file['format']

    def is_only_ism(presentation_videos):
        for video in presentation_videos['videos']:
            for file in video['files']:
                if file['format'] != 'video/x-mp4-fragmented':
                    return False
        return True

    def is_video_composition(presentation_videos):
        return len(presentation_videos['videos']) > 1

    def get_slides_infos(slides):
        global splited_url
        site_url = splited_url[0] + '//' + splited_url[2] + splited_url[3]
        slides_infos = {}
        if slides:
            content_server_id = slides.get('ContentServerId')
            presentation_id = slides.get('ParentResourceId')
            slides_dir = f"[{site_url}]/FileServer/{content_server_id}/Presentation/{presentation_id}"
            slides_urls = []
            for i in range(int(slides['Length']) + 1):
                #fill into 4 digits
                link = f'{slides_dir}/slide_{i+1:04}.jpg'
                slides_urls.append(link)
            slides_infos['urls'] = slides_urls
            slides_infos['details'] = slides['SlideDetails']
        return slides_infos

    def find_folder_path(folder_id, folders, path=''):
        """
        Provide the folder's path delimited by '/'
        by parsing the folders list structure

        params:
            folder_id: id of the folder for which we are looking for the path
        returns:
            string of the folder's path
        """

        for folder in folders:
            if folder['id'] == folder_id:
                path += find_folder_path(folder['parent_id'], folders, path)
                path += '/' + folder['name']
                return path
        return ''

    def make_data_structure(folders, parent_id=None, i=0):
        """
        Construct recursively a data representation of the folder-tree structure of Mediasite folders

        returns:
            list of dictionary items containing mediasite folder names, ID's, parent folder ID's,
            list of their child folders, and presentations
        """
        global iterations
        global videos_infos

        if not parent_id:
            logging.info('Getting folder tree.')
            parent_id = mediasite.folder.root_folder_id

        folder_tree = []
        for folder in folders:
            if folder['parent_id'] == parent_id:
                iterations += 1
                print('Requesting: ', f'{iterations} / {len(folders)} folders', end='\r', flush=True)
                logging.debug(f'Found child folder under parent: {parent_id}')
                child_folders = {
                    **folder,
                    'child_folders': make_data_structure(folders, folder['id'], iterations),
                    'presentations': mediasite.folder.get_folder_presentations(folder['id'])
                }
                folder_tree.append(child_folders)
        return folder_tree

    def order_presentations_by_folder(folders, parent_id=None):
        """
        Create a list of all folders in association with their presentations

        returns:
            list ot items containing folder ID, parent folder ID, name, and
                list of his presentations containing ID, title and owner
        """
        logging.info('Creating presentations by folders listing')
        if not parent_id:
            parent_id = mediasite.folder.root_folder_id

        i = 0
        presentations_folders = []
        for folder in folders:
            print('Requesting: ', f'{i} / {len(folders)} folders', end='\r', flush=True)
            presentations_folders.append({**folder,
                                          'presentations': mediasite.folder.get_folder_presentations(folder['id'])})
            i += 1
        return presentations_folders

    # ------------------------------- Script

    test_dir = 'tests/data'
    folders = mediasite.folder.get_all_folders()

    # Listing folders with their presentations
    try:
        with open('presentations_folders.json') as f:
            presentations_folders = json.load(f)
        if type(presentations_folders) is not list:
            raise FileNotFoundError
    except FileNotFoundError:
        with open('presentations_folders.json', 'w') as f:
            presentations_folders = order_presentations_by_folder(folders)
            json.dump(presentations_folders, f)

    # All videos infos
    try:
        with open('videos.json') as f:
            videos_infos = json.load(f)
        if type(videos_infos) is not list:
            raise FileNotFoundError
    except FileNotFoundError:
        with open('videos.json', 'w') as f:
            videos_infos = get_videos_infos(presentations_folders)
            json.dump(videos_infos, f)

    # Specific videos
    if options.stats:
        videos_stats = compute_videos_stats(videos_infos)
        print(videos_stats)

        # Videos ISM
        try:
            with open('videos_ism.json') as f:
                videos_ism = json.load(f)
            if type(videos_ism) is not list:
                raise FileNotFoundError
        except FileNotFoundError:
            videos_ism = []
            for video in videos_infos:
                videos_ism.append(video) if is_only_ism(video) else None
            with open('videos_ism.json', 'w') as f:
                json.dump(videos_ism, f)

        # Compositions videos
        try:
            with open('composition_videos.json') as f:
                composition_videos = json.load(f)
            if type(composition_videos) is not list:
                raise FileNotFoundError
        except FileNotFoundError:
            composition_videos = []
            for video in videos_infos:
                composition_videos.append(video) if is_video_composition(video) else None
            with open('composition_videos.json', 'w') as f:
                json.dump(composition_videos, f)
