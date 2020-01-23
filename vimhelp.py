# Retrieve a help page from the data store, and present to the user

import main
from dbmodel import ProcessedFileHead

from google.appengine.ext import ndb

import flask
import werkzeug.exceptions

import datetime
import logging
import threading

HTTP_NOT_MOD = 304
HTTP_MOVED_PERM = 301

LEGACY_URL_PREFIXES = \
    'http://www.vimhelp.org/', 'https://www.vimhelp.org/', \
    'http://vimhelp.appspot.com/', 'https://vimhelp.appspot.com/', \
    'http://vimhelp.org/'

g_cache = {}
g_cache_lock = threading.Lock()


@main.app.route('/<filename>')
def vimhelp_filename(filename):
    return vimhelp(filename)

@main.app.route('/')
def vimhelp_root():
    return vimhelp('')

@main.app.route('/_ah/warmup')
def vimhelp_warmup():
    return vimhelp('', is_warmup=True)

def vimhelp(filename, is_warmup=False):
    req = flask.request

    if req.url_root in LEGACY_URL_PREFIXES and not is_warmup:
        new_url = 'https://vimhelp.org' + req.script_root + req.full_path
        logging.info("redirecting to: %s", new_url)
        return redirect(new_url)

    if filename == 'help.txt.html':
        return redirect('/')
    elif not filename:
        filename = 'help.txt'
    elif not filename.endswith('.html'):
        flask.abort()
    else:
        filename = filename[:-5]  # strip ".html"

    if not filename.endswith('.txt') and filename != 'tags':
        logging.info("redirecting %s.html to %s.txt.html", filename, filename)
        return redirect('/' + filename + '.txt.html')

    logging.debug("filename: %s", filename)

    now = datetime.datetime.utcnow()

    with g_cache_lock:
        entry = g_cache.get(filename)

    if entry is not None:
        head, parts, timestamp = entry
        if next_update_time(timestamp) > now:
            logging.debug("responding from inproc cache entry")
            resp = prepare_response(req, head, now)
            return complete_response(resp, head, parts)
        logging.debug("inproc cache entry is expired")

    head = ProcessedFileHead.get_by_id(filename)
    if not head:
        logging.warn("%s not found in db", filename)
        raise werkzeug.exceptions.NotFound()
    logging.debug("responding from db")
    resp = prepare_response(req, head, now)
    parts = []
    if resp.status_code != HTTP_NOT_MOD:
        parts = get_parts(head)
        complete_response(resp, head, parts)
    if head.numparts == 1 or parts:
        logging.debug("writing entry to inproc cache")
        with g_cache_lock:
            g_cache[filename] = head, parts, now
    return resp


def prepare_response(req, head, now):
    resp = flask.Response()
    resp.set_etag(head.etag)
    expires = next_update_time(now)
    resp.expires = expires
    resp.last_modified = head.modified
    if head.etag in req.if_none_match:
        logging.info("matched etag, modified %s, expires %s",
                     resp.last_modified, expires)
        resp.status_code = HTTP_NOT_MOD
    elif not req.if_none_match and req.if_modified_since and \
            req.if_modified_since >= head.modified:
        logging.info("not modified since %s, modified %s, expires %s",
                     req.if_modified_since, resp.last_modified, expires)
        resp.status_code = HTTP_NOT_MOD
    return resp


# Return next exact half hour, i.e. HH:30:00 or HH:00:00
def next_update_time(t):
    r = t.replace(second=0, microsecond=0)
    r += datetime.timedelta(minutes=(30 - (t.minute % 30)))
    return r


def complete_response(resp, head, parts):
    logging.info("writing %d-part response, modified %s, expires %s",
                 1 + len(parts), resp.last_modified, resp.expires)
    resp.mimetype = 'text/html'
    resp.charset = head.encoding
    if resp.status_code != HTTP_NOT_MOD:
        resp.data = head.data0 + ''.join(p.data for p in parts)
    return resp


def redirect(url):
    return flask.redirect(url, HTTP_MOVED_PERM)


def get_parts(head):
    # We could alternatively achieve this via an ancestor query (retrieving the
    # head and its parts simultaneously) to give us strong consistency. But the
    # downside of that is that it bypasses the automatic memcache layer built
    # into ndb, which we want to take advantage of.
    if head.numparts == 1:
        return []
    logging.info("retrieving %d extra part(s)", head.numparts - 1)
    filename = head.key.string_id()
    keys = [ndb.Key('ProcessedFilePart', filename + ':' + str(i))
            for i in xrange(1, head.numparts)]
    num_tries = 0
    while True:
        num_tries += 1
        if num_tries >= 10:
            logging.error("tried too many times, giving up")
            raise werkzeug.exceptions.InternalServerError()
        parts = ndb.get_multi(keys)
        if any(p.etag != head.etag for p in parts):
            logging.warn("got differing etags, retrying")
        else:
            return sorted(parts, key=lambda p: p.key.string_id())
