import json
import logging
import argparse
from argparse import RawTextHelpFormatter
import os

from data_analyzer import DataAnalyzer
from lib.utils import MediasiteSetup

if __name__ == '__main__':
    # --------------------------- Setup
    # args
    def usage(message=''):
        return 'This script is used to extract metadata from mediasite platform'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=RawTextHelpFormatter)
        parser.add_argument('-i', '--info', action='store_true',
                            dest='info', default=False,
                            help='print more status messages to stdout.')
        parser.add_argument('-D', '--doctor', action='store_true',
                            dest='doctor', default=False,
                            help='check what presentations have not been acounted')
        parser.add_argument('-v', '--verbose', action='store_true',
                            dest='verbose', default=False,
                            help='print all status messages to stdout.')
        parser.add_argument('-d', '--dry-run', action='store_true',
                            dest='dryrun', default=False,
                            help='not really import medias.')

        return parser.parse_args()

    options = manage_opts()
    logger = MediasiteSetup.set_logger(options)

    #--------------------------- Script
    try:
        data = []
        with open('data.json') as f:
            data = json.load(f)
    except Exception as e:
        logging.debug(e)
        logging.error('No data to analyse, or data is corrupted. Please run import data process:\n \
                       $ make import_data')
        run_import = input('Do you want to run import data right now ? y/N').lower()
        if run_import == 'y' or run_import == 'yes':
            os.system("make import_data")

    analyzer = DataAnalyzer(data)

    print(f'Found {len(analyzer.folders)} folders')
    print(f'Number of presentations in folders: {len(analyzer.presentations)}')

    folders_infos = analyzer.analyse_folders()
    empty_folders = folders_infos['empty_folders']
    empty_user_folders = folders_infos['empty_user_folders']
    print(f'{len(empty_folders)} folders have no presentation inside {len(empty_user_folders)} user folders')

    videos_format_stats = analyzer.compute_videos_stats()
    with_mp4 = 0
    no_mp4 = 0
    for v_format, count in videos_format_stats.items():
        if v_format == 'video/mp4':
            with_mp4 = count
        else:
            no_mp4 += count
    print(f'{no_mp4}% of videos without mp4 vs {with_mp4}% with mp4')

    videos_layout_stats = analyzer.compute_layout_stats()
    no_slide = videos_layout_stats['mono']
    with_slides = videos_layout_stats['mono + slides']
    multiple = videos_layout_stats['multiple']
    print(f'There\'s {no_slide}% of videos with no slide, {with_slides}% with slides, and {multiple}% are compositions of multiple videos')

    mp4_analyse = analyzer.analyse_downloadable_mp4()
    downloadable_mp4 = mp4_analyse['downloadable_mp4']
    status_codes = mp4_analyse['status_codes']
    print(f'{len(downloadable_mp4)} downloadable mp4s, status codes: {status_codes}')

    if options.doctor:
        config_data = {}
        try:
            with open('config.json') as js:
                config_data = json.load(js)
        except Exception as e:
            logging.debug(e)
        mediasite = MediasiteSetup(config_data).mediasite

        # Listing all presentations
        print('Listing all presentations...')
        all_presentations = mediasite.presentation.get_all_presentations()

        # Listing presentations that are not referenced in folders
        presentations_in_folders = analyzer.presentations
        presentations_not_in_folders = []
        for presentation_1 in all_presentations:
            found = False
            for presentation_2 in presentations_in_folders:
                if presentation_1['id'] == presentation_2['id']:
                    found = True
                    break
            if not found:
                presentations_not_in_folders.append(presentation_1)

        print(f'''All presentations found in Mediasite platform : {len(all_presentations)}
                Presentations not accounted : {len(presentations_not_in_folders)}.''')
