#!/usr/bin/env python3
import requests


def get_session(user, password, headers=dict()):
    session = requests.session()
    session.auth = requests.auth.HTTPBasicAuth(user, password)
    session.headers = headers
    return session


def url_exists(url, session):
    r = session.head(url)
    return r.ok and int(r.headers.get('Content-Length', 0)) > 0
