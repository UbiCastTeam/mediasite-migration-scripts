import os
import logging
from datetime import datetime



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

def set_logger(options, run_path=None):
    if run_path is None:
        run_path = os.path.dirname(os.path.realpath(__file__))
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

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    logs_folder = f'{run_path}/logs/'
    os.makedirs(logs_folder, exist_ok=True)
    logfile_path = os.path.join(logs_folder, f'test_{current_datetime_string}.log')
    logfile = logging.FileHandler(logfile_path)
    logfile.setFormatter(formatter)

    logger.addHandler(logfile)
    logger.addHandler(console)

    return logger