import argparse
import json
import os
import logging
from datetime import datetime
import csv


logger = logging.getLogger(__name__)

RED, GREEN, YELLOW, BLUE, WHITE, LIGHT_RED = [1, 2, 3, 4, 67, 61]

# The background is set with 40 plus the number of the color, and the foreground with 30
#  31 Red 32 Green 33 Yellow 34 Blue 91 Light Red 97 White

#These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"


def formatter_message(message, use_color=True):
    if use_color:
        message = message.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
    else:
        message = message.replace("$RESET", "").replace("$BOLD", "")
    return message


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


def parse_mediasite_date(date_str):
    #2010-05-26T07:16:57Z
    if '.' in date_str:
        # some media have msec included
        #2016-12-07T13:07:27.58Z
        date_str = date_str.split('.')[0] + 'Z'
    if not date_str.endswith('Z'):
        date_str += 'Z'
    return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')


def get_age_days(date_str):
    days = (datetime.now() - parse_mediasite_date(date_str)).days
    return days


def set_logger(options=None, verbose=False, run_path=None):
    if run_path is None:
        run_path = os.path.dirname(os.path.realpath(__file__))
    current_datetime_string = '{dt.month}-{dt.day}-{dt.year}'.format(dt=datetime.now())
    logging_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging_datefmt = '%m/%d/%Y - %I:%M:%S %p'
    formatter = logging.Formatter(logging_format, datefmt=logging_datefmt)
    colored_formatter = ColoredFormatter(logging_format, datefmt=logging_datefmt)

    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    elif options:
        if options.verbose:
            level = logging.DEBUG
        elif options.quiet:
            level = logging.ERROR

    root_logger = logging.getLogger('root')
    root_logger.setLevel(level)

    if not root_logger.handlers:
        console = logging.StreamHandler()
        console.setFormatter(colored_formatter)

        logs_folder = 'logs/'
        os.makedirs(logs_folder, exist_ok=True)
        logfile_path = os.path.join(logs_folder, f'test_{current_datetime_string}.log')
        logfile = logging.FileHandler(logfile_path)
        logfile.setFormatter(formatter)

        root_logger.addHandler(logfile)
        root_logger.addHandler(console)

    return root_logger


def is_folder_to_add(path, config={}):
    if config.get('whitelist'):
        for fw in config['whitelist']:
            if fw in path:
                return True
        return False
    return True


def read_json(path):
    logging.info(f'Loading {path}')
    with open(path, 'r') as f:
        return json.load(f)


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
def write_csv(file, fieldnames, rows):
    with open(file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# FIXME: unify
def setup_logging(verbose=False):
    logging.addLevelName(logging.ERROR, '\033[1;31m%s\033[1;0m' % logging.getLevelName(logging.ERROR))
    logging.addLevelName(logging.WARNING, '\033[1;33m%s\033[1;0m' % logging.getLevelName(logging.WARNING))
    level = getattr(logging, 'DEBUG' if verbose else 'INFO')
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)-8s %(message)s',
    )


def get_progress_string(index, total):
    percent = 100 * (index) / total
    return f'[{index + 1}/{total} ({percent:.1f}%)]'


def get_timecode_from_sec(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    timecode = "%d:%02d:%02d" % (h, m, s)
    return timecode


def get_mediasite_host(url):
    return url.split('/')[2]

<<<<<<< HEAD

def get_argparser():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Print all information to stdout.',
    )
    return parser
=======
>>>>>>> write failed presentations report into CSV refs #34128
