#!/usr/bin/env python3

def url_exists(url, session):
    r = session.head(url)
    return r.ok and int(r.headers.get('Content-Length', 0)) > 0
