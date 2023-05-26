# Retrieve a help page from the data store, and present to the user

import logging
from http import HTTPStatus

import flask
import werkzeug.exceptions

from google.cloud import ndb

from . import dbmodel
from . import vimh2h


def handle_vimhelp(filename, cache):
    req = flask.request
    project = flask.g.project

    if filename in ("help.txt", "help"):
        return redirect("./")

    if filename == "":
        filename = "help.txt"

    if not filename.endswith(".txt") and filename != "tags":
        return redirect(f"{filename}.txt.html")

    theme = req.cookies.get("theme")
    if theme not in ("light", "dark"):
        theme = None

    if entry := cache.get(project, filename):
        logging.info("serving '%s:%s' from inproc cache", project, filename)
        head, parts = entry
        resp = prepare_response(req, head, theme)
        return complete_response(resp, head, parts, theme)

    with dbmodel.ndb_context():
        logging.info("serving '%s:%s' from datastore", project, filename)
        head = dbmodel.ProcessedFileHead.get_by_id(f"{project}:{filename}")
        if head is None:
            logging.warning("%s:%s not found in datastore", project, filename)
            raise werkzeug.exceptions.NotFound()
        resp = prepare_response(req, head, theme)
        parts = []
        if resp.status_code != HTTPStatus.NOT_MODIFIED:
            parts = get_parts(head)
            complete_response(resp, head, parts, theme)
        if head.numparts == 1 or parts:
            cache.put(project, filename, (head, parts))
        return resp


def prepare_response(req, head, theme):
    resp = flask.Response(mimetype="text/html")
    resp.last_modified = head.modified
    resp.cache_control.max_age = 15 * 60
    resp.vary.add("Cookie")
    resp.set_etag(head.etag.decode() + (theme or ""))
    return resp.make_conditional(req)


def complete_response(resp, head, parts, theme):
    if resp.status_code != HTTPStatus.NOT_MODIFIED:
        logging.info(
            "writing %d-part response, modified %s",
            1 + len(parts),
            resp.last_modified,
        )
        prelude = vimh2h.VimH2H.prelude(theme=theme).encode()
        resp.data = b"".join((prelude, head.data0, *(p.data for p in parts)))
    return resp


def redirect(url):
    logging.info("redirecting %s to %s", flask.request.path, url)
    return flask.redirect(url, HTTPStatus.MOVED_PERMANENTLY)


def get_parts(head):
    # We could alternatively achieve this via an ancestor query (retrieving the head and
    # its parts simultaneously) to give us strong consistency.
    if head.numparts == 1:
        return []
    logging.info("retrieving %d extra part(s)", head.numparts - 1)
    head_id = head.key.id()
    keys = [
        ndb.Key("ProcessedFilePart", f"{head_id}:{i}") for i in range(1, head.numparts)
    ]
    num_tries = 0
    while True:
        parts = ndb.get_multi(keys)
        if all(p.etag == head.etag for p in parts):
            return sorted(parts, key=lambda p: p.key.string_id())
        num_tries += 1
        if num_tries >= 10:
            logging.error("tried too many times, giving up")
            raise werkzeug.exceptions.InternalServerError()
        logging.warning("got differing etags, retrying")
