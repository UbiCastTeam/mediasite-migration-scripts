#!/usr/bin/env python3
import requests
import logging

logger = logging.getLogger(__name__)


def get_session(user, password, headers=dict()):
    session = requests.session()
    session.auth = requests.auth.HTTPBasicAuth(user, password)
    session.headers = headers
    return session


def url_exists(url, session):
    try:
        r = session.head(url, headers={'Accept-Encoding': None})
    except Exception as e:
        logger.error(f'Failed to reach url [{url}] : {e}')
        return False
    return r.ok and int(r.headers.get('Content-Length', 0)) > 0
