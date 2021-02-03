from argparse import RawTextHelpFormatter
import argparse
import logging

if __name__ == '__main__':
    # Args
    def usage(message=''):
        return 'This script is used to make statistics about video format and layout in Mediasite platform'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=RawTextHelpFormatter)
        parser.add_argument('-i', '--info', action='store_true',
                            dest='info', default=False,
                            help='print more status messages to stdout.')
        parser.add_argument('-v', '--verbose', action='store_true',
                            dest='verbose', default=False,
                            help='print all status messages to stdout.')

        return parser.parse_args()

    options = manage_opts()

    # Script

    if options.stats:
        videos_infos = []
        for folder in data:
            for prez in folder['presentations']:
                videos_infos.append(prez)
        videos_formats_stats = compute_videos_stats(videos_infos)
        videos_type_stats = compute_global_stats(videos_infos)
        print(f'Formats : {videos_formats_stats}', f'Types of videos : {videos_type_stats}', sep='\n')

        # Videos ISM (smooth streaming)
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

        # Compositions videos (multiple)
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

