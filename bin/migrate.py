#!/usr/bin/env python3
import argparse
import os
import sys
import logging
import traceback

from mediatransfer import MediaTransfer
import mediasite_migration_scripts.utils.common as utils

if __name__ == '__main__':
    def usage(message=''):
        return 'This script is used to import media from mediasite to mediaserver'

    def manage_opts():
        parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

        parser.add_argument(
            '-q',
            '--quiet',
            action='store_true',
            dest='quiet', default=False,
            help='Be less verbose.'
        )
        parser.add_argument(
            '-v',
            '--verbose',
            action='store_true',
            dest='verbose', default=False,
            help='Be very verbose.'
        )
        parser.add_argument(
            '--max-videos',
            default=None,
            help='Stop after uploading this amount of videos (useful for quick testing).'
        )
        parser.add_argument(
            '--config-file',
            default='config.json',
            help='Path to config file (see config.json.example).'
        )
        parser.add_argument(
            '--mediasite-file',
            default='data/mediasite_all_data.json',
            help='Path to mediasite data file.'
        )
        parser.add_argument(
            '--always-check-remote',
            action='store_true',
            default=False,
            help='''Do not skip uploads if they are referenced in mediaserver_data.json or redirection.json ;
                 instead, MediaServer will be queried to check if media have already been uploaded.
                 Use it if the redirection or mediaserver data files are outdated.'''
        )
        parser.add_argument(
            '--download-folder',
            type=str,
            help='Folder name for downloads. Will be created if needed.',
            default='downloads',
        )
        parser.add_argument(
            '--skip-userfolders',
            action='store_true',
            default=False,
            help='Skip importing user folders.'
        )
        parser.add_argument(
            '--skip-composites',
            action='store_true',
            default=False,
            help='Skip importing composite videos.'
        )
        parser.add_argument(
            '--skip-others',
            action='store_true',
            default=False,
            help='Skip importing media that are not composite videos.'
        )
        return parser.parse_args()

    options = manage_opts()
    utils.set_logger(options=options)

    logger = logging.getLogger(__name__)

    logger.info('----- START SCRIPT' + 50 * '-')
    logger.debug(f'Starting {__file__}')

    mediasite_file = options.mediasite_file
    if not os.path.exists(mediasite_file):
        should_import = input(f'No metadata file found at {mediasite_file}. You need to import Mediasite metadata first.\nDo you want to run import ? [y/N] ')
        should_import = should_import.lower()
        if should_import == 'y' or should_import == 'yes':
            args = ' '.join(sys.argv[1:])
            os.system(f'python3 bin/collect.py {args}')
        else:
            logger.error('--------- Aborted ---------')
            sys.exit(1)

    config_file = options.config_file
    try:
        config = utils.read_json(config_file)
    except Exception:
        logger.error(f'Failed to parse config file {config_file}.')
        logger.error('--------- Aborted ---------')
        sys.exit(1)

    # push args into config object for easier access
    # be careful about name conflicts between config file
    # and argument variables
    config.update(vars(options))

    try:
        mediasite_data = utils.read_json(mediasite_file)
    except Exception:
        logger.error(f'Failed to parse Mediasite {mediasite_file}')
        logger.error('--------- Aborted ---------')
        sys.exit(1)

    mediatransfer = MediaTransfer(config, mediasite_data)

    logger.info('Uploading videos')
    try:
        uploaded_medias_stats = mediatransfer.upload_medias(options.max_videos)
        logger.info(f'Upload successful: \n {uploaded_medias_stats}')
    except KeyboardInterrupt:
        logger.warning('Interrupted by the user')
    except Exception as e:
        logger.error(f'Error during upload: {e}')
        traceback.print_exc()

    # ensure that we save redirections even if we crashed
    mediatransfer.write_redirections_file()
    mediatransfer.dump_incomplete_media()

    logger.info('----- END SCRIPT ' + 50 * '-' + '\n')
