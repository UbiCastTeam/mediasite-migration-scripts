#!/usr/bin/env python3
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
        for index, sf in enumerate(subfolders):
            logging.info(utils.get_progress_string(index, total) + f' Merging {sf.name}')
            self.merge(sf)

    def merge(self, media_folder):
        logging.debug(f'Merging videos in folder : {media_folder}')
        layout_file = media_folder / 'mediaserver_layout.json'
        if not layout_file.is_file():
            cmd = f'python3 bin/merge.py --width {self.config.get("composite_width", 1920)} --height {self.config.get("composite_height", 1080)} {media_folder}'
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
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        '-v',
        '--verbose',
        help='set verbosity to DEBUG',
        action='store_true'
    )

    parser.add_argument(
        'folder',
        type=str,
        help='Folder name in which to look for media (single media)',
    )

    parser.add_argument(
        '--config-file',
        default='config.json',
    )

    args = parser.parse_args()
    utils.setup_logging(args.verbose)
    config = utils.read_json(args.config_file)
    config.update(vars(args))
    try:
        b = BatchMerge(config)
    except KeyboardInterrupt:
        logging.info('Interrupted')
