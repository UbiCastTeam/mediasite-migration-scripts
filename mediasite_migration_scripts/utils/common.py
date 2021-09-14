import argparse
import json
import os
import logging
from datetime import datetime
import csv
from pathlib import Path

logger = logging.getLogger(__name__)

# codes colors
RED, GREEN, YELLOW, BLUE, WHITE, LIGHT_RED = [1, 2, 3, 4, 67, 61]

# The background is set with 40 plus the code color:
# 31 : Red, 32 : Green, 33 : Yellow, 34 : Blue, 91 : Light Red, 97 : White

#These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

COLORS = {
    'WARNING': YELLOW,
    'INFO': WHITE,
    'DEBUG': BLUE,
    'ERROR': LIGHT_RED,
    'CRITICAL': RED,
}


class ColoredFormatter(logging.Formatter):
    def __init__(self, msg, use_color=True, datefmt=None):
        logging.Formatter.__init__(self, msg, datefmt=datefmt)
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in COLORS:
            levelname_color = COLOR_SEQ % (30 + COLORS[levelname]) + levelname + RESET_SEQ
            record.levelname = levelname_color
        return logging.Formatter.format(self, record)


def set_logger(options=None, verbose=False):
    logging_format = '%(asctime)s - %(levelname)s - %(message)s'
    level = logging.INFO
    if options is not None:
        if options.verbose:
            level = logging.DEBUG
            logging_format += ' - [%(funcName)s]'
        elif options.quiet:
            level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
        logging_format += ' - [%(funcName)s]'

    current_datetime_string = '{dt.month}-{dt.day}-{dt.year}'.format(dt=datetime.now())

    logging_datefmt = '%m/%d/%Y - %I:%M:%S %p'
    formatter = logging.Formatter(logging_format, datefmt=logging_datefmt)
    colored_formatter = ColoredFormatter(logging_format, datefmt=logging_datefmt)

    root_logger = logging.getLogger('root')
    root_logger.setLevel(level)
    if not root_logger.handlers:
        console = logging.StreamHandler()
        console.setFormatter(colored_formatter)

        logs_folder = 'logs/'
        os.makedirs(logs_folder, exist_ok=True)
        logfile_path = os.path.join(logs_folder, f'{current_datetime_string}.log')
        logfile = logging.FileHandler(logfile_path)
        logfile.setFormatter(formatter)

        root_logger.addHandler(logfile)
        root_logger.addHandler(console)

    return root_logger


def is_folder_to_add(path, config=dict()):
    if config.get('whitelist'):
        for whitelisted_path in config['whitelist']:
            if whitelisted_path in path:
                return True
        return False
    return True


def read_json(path):
    logging.info(f'Loading {path}')
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f'Failed to read json {path}: {e}')


def write_json(data, path, open_text_option='w'):
    logger.info(f'Writing {path}')
    try:
        with open(path, open_text_option) as file:
            json.dump(data, file)
    except IOError:
        parent = Path(path).parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, open_text_option) as file:
                json.dump(data, file)
        except Exception as e:
            logger.error(f'Failed to write json {path}: {e}')
    except Exception as e:
        logger.error(f'Failed to write json {path}: {e}')


def write_csv(filename, fieldnames, rows):
    logger.info(f'Writing {filename}')
    try:
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        logger.error(f'Failed to write csv {filename}: {e}')


def store_object_data_in_json(obj, data_attr, prefix_filename=str()):
    mediasite_filename = ''.join([prefix_filename, '_', data_attr, '.json'])
    mediasite_data = getattr(obj, data_attr)
    write_json(data=mediasite_data, path=mediasite_filename)


def to_mediaserver_conf(config):
    msconfig = {
        'API_KEY': config.get('mediaserver_api_key', ''),
        'CLIENT_ID': 'mediasite-migration-client',
        'SERVER_URL': config.get('mediaserver_url', ''),
        'VERIFY_SSL': False,
        'LOG_LEVEL': 'WARNING',
        'TIMEOUT': 120,
        'MAX_RETRY': 3,
    }
    return msconfig


def get_progress_string(index, total):
    if total <= 0:
        return ''
    percent = 100 * (index) / total
    return f'[{index + 1}/{total} ({percent:.1f}%)]'


def print_progress_string(index, total, title=str()):
    progress_string = get_progress_string(index, total)
    print(progress_string, title, end='\r')


def get_timecode_from_sec(seconds):
    if seconds < 0:
        h, m, s = 0, 0, 0
    else:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
    timecode = "%d:%02d:%02d" % (h, m, s)

    return timecode


def get_mediasite_host(url):
    return url.split('/')[2]


def get_argparser():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Print all information to stdout.',
    )
    return parser
