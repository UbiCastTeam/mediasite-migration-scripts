#!/usr/bin/env python3
import time
import argparse
import logging
import subprocess
from pathlib import Path
import mediasite_migration_scripts.utils.common as utils


class BatchMerge:
    def __init__(self, config):
        self.config = config
        path = Path(config["folder"])
        subfolders = [d for d in path.iterdir() if d.is_dir()]
        total = len(subfolders)
        failed = list()
        before = time.time()
        for index, sf in enumerate(subfolders):
            logging.info(utils.get_progress_string(index, total) + f' Merging {sf.name}')
            if not self.merge(sf):
                failed.append(sf.name)
        took_s = time.time() - before
        took_per_media = utils.get_timecode_from_sec(took_s / total)
        logging.info(f'Finished processing {total} media, took {utils.get_timecode_from_sec(took_s)} ({took_per_media} per media)')
        if failed:
            logging.error(f'{len(failed)} failed / {total}: {failed}')

    def merge(self, media_folder):
        logging.debug(f'Merging videos in folder : {media_folder}')
        layout_file = media_folder / 'mediaserver_layout.json'
        if not layout_file.is_file():
            cmd = f'python3 bin/merge.py --width {self.config.get("composite_width", 1920)} --height {self.config.get("composite_height", 1080)} --max-duration={self.config["max_duration"]} {media_folder}'
            logging.debug(cmd)
            return_code, output = subprocess.getstatusoutput(cmd)
            if return_code != 0:
                logging.error(f'Failed: {cmd}:\n{output}')
            else:
                logging.debug(output)
        else:
            logging.info(f'{layout_file} already found, skipping merge')
            return_code = 0
        return (return_code == 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-v',
        '--verbose',
        help='set verbosity to DEBUG',
        action='store_true'
    )

    parser.add_argument(
        'folder',
        type=str,
        help='Folder name in which to look for media folders',
    )

    parser.add_argument(
        '--config-file',
        default='config.json',
    )

    parser.add_argument(
        '--max-duration',
        type=int,
        help='Stop after this amount of seconds (disabled by default). Can be useful for looking at results quicker.',
        default=0,
    )

    args = parser.parse_args()
    utils.setup_logging(args.verbose)
    config = utils.read_json(args.config_file)
    config.update(vars(args))
    try:
        b = BatchMerge(config)
    except KeyboardInterrupt:
        logging.info('Interrupted')
