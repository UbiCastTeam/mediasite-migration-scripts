#!/usr/bin/env python3
import argparse
import json
import os
import sys
import logging

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
            default='mediasite_data.json',
            help='Path to mediasite data file.'
        )
        parser.add_argument(
            '--mediaserver-file',
            default='mediaserver_data.json',
            help='Path to mediaserver data file (output).'
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
        run_import = input(f'No metadata file found at {mediasite_file}. You need to import Mediasite metadata first.\nDo you want to run import ? [y/N] ')
        run_import = run_import.lower()
        if run_import == 'y' or run_import == 'yes':
            args = ' '.join(sys.argv[1:])
            os.system(f'python3 bin/import_data.py {args}')
        else:
            logger.error('--------- Aborted ---------')
            sys.exit(1)

    config_file = options.config_file
    try:
        with open(config_file) as f:
            config = json.load(f)
    except Exception as e:
        logger.debug(e)
        logger.error(f'Failed to parse config file {config_file}.')
        logger.error('--------- Aborted ---------')
        sys.exit(1)

    # push args into config object for easier access
    # be careful about name conflicts between config file
    # and argument variables
    config.update(vars(options))

    try:
        with open(mediasite_file) as f:
            mediasite_data = json.load(f)
    except Exception as e:
        logger.error(f'Failed to parse Mediasite {mediasite_file}')
        logger.error(e)
        logger.error('--------- Aborted ---------')
        sys.exit(1)

    mediatransfer = MediaTransfer(config, mediasite_data)

    logger.info('Uploading videos')
    try:
        nb_uploaded_medias = mediatransfer.upload_medias(options.max_videos)
        logger.info(f'Upload successful: uploaded {nb_uploaded_medias} medias')
    except KeyboardInterrupt:
        logger.warning('Interrupted by the user')
    except Exception as e:
        logger.error(f'Error during upload: {e}')

    # ensure that we save redirections even if we crashed
    mediatransfer.write_redirections_file()

    if options.verbose:
        mediaserver_data = mediatransfer.mediaserver_data
        mediaserver_file = options.mediaserver_file
        try:
            with open(mediaserver_file, 'w') as f:
                json.dump(mediaserver_data, f)
        except Exception as e:
            logger.error('Failed to save Mediaserver mapping')
            logger.debug(e)
            sys.exit(1)

    logger.info('----- END SCRIPT ' + 50 * '-' + '\n')
