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
    iterations = 0

    def order_presentations_by_folder(folders, parent_id=None):
        """
        Create a list of all folders in association with their presentations

        returns:
            list ot items containing folder ID, parent folder ID, name, and
                list of his presentations containing ID, title and owner
        """
        logging.info('Gathering and ordering all presentations infos ')
        if not parent_id:
            parent_id = mediasite.folder.root_folder_id

        i = 0
        presentations_folders = []
        for folder in folders:
            print('Requesting: ', round(i / len(folders) * 100, 1), '%', end='\r', flush=True)
            presentations = mediasite.folder.get_folder_presentations(folder['id'])

            for presentation in presentations:
                presentation['videos'] = get_videos_infos(presentation)
                presentation['slides'] = get_slides_infos(presentation)
            presentations_folders.append({**folder,
                                          'path': find_folder_path(folder['id'], folders),
                                          'presentations': presentations})
            i += 1
        return presentations_folders

    def get_videos_infos(presentation):
        logging.debug(f"Gathering video info for presentation : {presentation['id']}")

        videos_infos = []
        video = mediasite.presentation.get_presentation_content(presentation['id'], 'OnDemandContent')
        videos_infos = get_video_detail(video)
        return videos_infos

    def get_video_detail(video):
        video_list = []
        if video:
            for file in video['value']:
                content_server = mediasite.presentation.get_content_server(file['ContentServerId'])
                if 'DistributionUrl' in content_server:
                    # popping odata query params, we just need the route
                    splitted_url = content_server['DistributionUrl'].split('/')
                    splitted_url.pop()
                    storage_url = '/'.join(splitted_url)
                else:
                    storage_url = None

                file_name = file['FileNameWithExtension']
                video_url = os.path.join(storage_url, file_name) if file_name and storage_url else None
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

    def compute_videos_stats(presentations):
        count = {}
        for video in presentations:
            video_format = find_best_format(video)
            if video_format in count:
                count[video_format] += 1
            else:
                count[video_format] = 1

        stats = {}
        for v_format, v_count in count.items():
            stats[v_format] = str(round((v_count / len(presentations)) * 100)) + '%'
        return stats

    def compute_global_stats(presentations):
        stats = {'mono': 0, 'mono + slides': 0, 'multiple': 0}
        for presentation in presentations:
            if is_video_composition(presentation):
                stats['multiple'] += 1
            elif len(presentation['slides']) > 0:
                stats['mono + slides'] += 1
            else:
                stats['mono'] += 1
        for stat, count in stats.items():
            stats[stat] = str(round((count / len(presentations) * 100))) + '%'

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

    def get_slides_infos(presentation, details=False):
        logging.debug(f"Gathering slides infos for presentation: {presentation['id']}")

        slides_infos = {}
        option = 'SlideDetailsContent' if details else 'SlideContent'
        slides_result = mediasite.presentation.get_presentation_content(presentation['id'], option)
        if slides_result:
            for slides in slides_result['value']:
                content_server_id = slides['ContentServerId']
                content_server = mediasite.presentation.get_content_server(content_server_id, slide=True)
                content_server_url = content_server['Url']
                presentation_id = slides['ParentResourceId']

                slides_base_url = f"{content_server_url}/{content_server_id}/Presentation/{presentation_id}"
                slides_urls = []
                slides_files_names = slides['FileNameWithExtension']
                for i in range(int(slides['Length'])):
                    # Transform string format (from C# to Python syntax) -> slides_{0:04}.jpg
                    file_name = slides_files_names.replace('{0:D4}', f'{i+1:04}')
                    link = f'{slides_base_url}/{file_name}'
                    slides_urls.append(link)

                slides_infos['urls'] = slides_urls
                slides_infos['details'] = slides['SlideDetails'] if details else None

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

    def find_presentations_not_in_folder(presentations, presentations_folders):
        presentations_not_in_folders = list()
        for prez in presentations:
            found = False
            i = 0
            while not found and i < len(presentations_folders):
                if prez['id'] == presentations_folders[i]['id']:
                    found = True
                i += 1
            if not found:
                presentations_not_in_folders.append(prez)

        return presentations_not_in_folders

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

    # ------------------------------- Script

    test_dir = 'tests/data'

    # Listing all presentations
    try:
        with open('presentations.json') as f:
            presentations = json.load(f)
    except Exception as e:
        logging.debug(e)
        with open('presentations.json', 'w') as f:
            presentations = mediasite.presentation.get_all_presentations()
            json.dump(presentations, f)

    # Listing folders with their presentations
    try:
        with open('data.json') as f:
            data = json.load(f)
            logging.info('data.json already found, not fetching catalog data')
    except Exception as e:
        logging.debug(e)
        folders = mediasite.folder.get_all_folders()
        with open('data.json', 'w') as f:
            data = order_presentations_by_folder(folders)
            json.dump(data, f)

    # Listing presentations that are not referenced in folders
    presentations_not_in_folders = list()
    try:
        with open('presentations_not_in_folders.json') as f:
            presentations_not_in_folders = json.load(f)
    except Exception as e:
        logging.debug(e)
        with open('presentations_not_in_folders.json', 'w') as f:
            presentations_in_folders = []
            for folder in data:
                for prez in folder['presentations']:
                    presentations_in_folders.append(prez)

            presentations_not_in_folders = find_presentations_not_in_folder(presentations, presentations_in_folders)
            json.dump(presentations_not_in_folders, f)

    # Stats
    if options.stats:
        videos_infos = []
        for folder in data:
            for prez in folder['presentations']:
                videos_infos.append(prez)
        videos_formats_stats = compute_videos_stats(videos_infos)
        videos_type_stats = compute_global_stats(videos_infos)
        print(f'Formats : {videos_formats_stats}', f'Types of videos : {videos_type_stats}', sep='\n')

        # Videos ISM
        try:
            with open('videos_ism.json') as f:
                videos_ism = json.load(f)
        except Exception as e:
            logging.debug(e)
            videos_ism = []
            for video in videos_infos:
                videos_ism.append(video) if is_only_ism(video) else None
            with open('videos_ism.json', 'w') as f:
                json.dump(videos_ism, f)

        # Compositions videos
        try:
            with open('composition_videos.json') as f:
                composition_videos = json.load(f)
        except Exception as e:
            logging.debug(e)
            composition_videos = []
            for video in videos_infos:
                composition_videos.append(video) if is_video_composition(video) else None
            with open('composition_videos.json', 'w') as f:
                json.dump(composition_videos, f)
