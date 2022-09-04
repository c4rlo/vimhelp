# Retrieve a help page from the data store, and present to the user

import datetime
import logging
from http import HTTPStatus

import flask
import werkzeug.exceptions

from google.cloud import ndb

from . import dbmodel
from . import util


def handle_vimhelp(filename, cache):
    req = flask.request

    if not filename:
        filename = "help.txt"
    elif not filename.endswith(".html"):
        raise werkzeug.exceptions.NotFound()
    else:
        filename = filename[:-5]  # strip ".html"

    if not filename.endswith(".txt") and filename != "tags":
        logging.info("redirecting %s.html to %s.txt.html", filename, filename)
        return redirect(f"/{filename}.txt.html")

    logging.info("filename: %s", filename)

    if entry := cache.get(filename):
        logging.info("responding from inproc cache entry")
        head, parts = entry
        resp = prepare_response(req, head, datetime.datetime.utcnow())
        return complete_response(resp, head, parts)

    with dbmodel.ndb_client.context():
        head = dbmodel.ProcessedFileHead.get_by_id(filename)
        if not head:
            logging.warn("%s not found in db", filename)
            raise werkzeug.exceptions.NotFound()
        logging.info("responding from db")
        now = datetime.datetime.utcnow()
        resp = prepare_response(req, head, now)
        parts = []
        if resp.status_code != HTTPStatus.NOT_MODIFIED:
            parts = get_parts(head)
            complete_response(resp, head, parts)
        if head.numparts == 1 or parts:
            cache.put(filename, (head, parts))
        return resp


def prepare_response(req, head, now):
    resp = flask.Response(mimetype="text/html")
    resp.charset = head.encoding
    resp.last_modified = head.modified
    resp.expires = util.next_update_time(now)
    resp.set_etag(head.etag.decode())
    return resp.make_conditional(req)


def complete_response(resp, head, parts):
    if resp.status_code != HTTPStatus.NOT_MODIFIED:
        logging.info(
            "writing %d-part response, modified %s, expires %s",
            1 + len(parts),
            resp.last_modified,
            resp.expires,
        )
        resp.data = head.data0 + b"".join(p.data for p in parts)
    return resp


def redirect(url):
    return flask.redirect(url, HTTPStatus.MOVED_PERMANENTLY)


def get_parts(head):
    # We could alternatively achieve this via an ancestor query (retrieving the head and
    # its parts simultaneously) to give us strong consistency. But the downside of that
    # is that it bypasses the automatic memcache layer built into ndb, which we want to
    # take advantage of.
    if head.numparts == 1:
        return []
    logging.info("retrieving %d extra part(s)", head.numparts - 1)
    filename = head.key.string_id()
    keys = [
        ndb.Key("ProcessedFilePart", filename + ":" + str(i))
        for i in range(1, head.numparts)
    ]
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
