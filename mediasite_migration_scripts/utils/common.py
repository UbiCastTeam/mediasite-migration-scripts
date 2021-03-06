import os
import logging
from datetime import datetime

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
    if options:
        if options.verbose:
            level = logging.DEBUG
        elif options.quiet:
            level = logging.ERROR
    elif verbose:
        level = logging.DEBUG

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
