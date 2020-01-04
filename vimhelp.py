# Retrieve a help page from the data store, and present to the user

import datetime
import logging
import threading
import webapp2
from webob.exc import HTTPNotFound, HTTPInternalServerError
from google.appengine.ext import ndb
from dbmodel import ProcessedFileHead

HTTP_NOT_MOD = 304

LEGACY_HOSTS = 'www.vimhelp.org', 'vimhelp.appspot.com'
LEGACY_HOST_URLS = ('http://vimhelp.org',)

g_cache = {}
g_cache_lock = threading.Lock()


class PageHandler(webapp2.RequestHandler):
    def get(self, filename):
        req = self.request
        resp = self.response

        if req.host in LEGACY_HOSTS or req.host_url in LEGACY_HOST_URLS:
            new_url = 'https://vimhelp.org' + req.path_qs
            logging.info("Redirecting to: {}".format(new_url))
            return self.redirect(new_url, permanent=True)
        if filename == 'help.txt':
            return self.redirect('/', permanent=True)
        if not filename:
            filename = 'help.txt'
        elif not filename.endswith('.txt') and filename != 'tags':
            return self.redirect('/' + filename + '.txt.html', permanent=True)

        now = datetime.datetime.utcnow()

        with g_cache_lock:
            entry = g_cache.get(filename)

        if entry is not None:
            head, parts, timestamp = entry
            if next_update_time(timestamp) > now:
                logging.debug("responding from inproc cache entry")
                prepare_response(req, resp, head, now)
                if resp.status_int != HTTP_NOT_MOD:
                    write_response(resp, head, parts)
            else:
                logging.debug("inproc cache entry is expired")
                entry = None

        if entry is None:
            head = ProcessedFileHead.get_by_id(filename)
            if not head:
                logging.warn("%s not found in db", filename)
                raise HTTPNotFound()
            logging.debug("responding from db")
            prepare_response(req, resp, head, now)
            parts = []
            if resp.status_int != HTTP_NOT_MOD:
                parts = get_parts(head)
                write_response(resp, head, parts)
            if head.numparts == 1 or parts:
                logging.debug("writing entry to inproc cache")
                with g_cache_lock:
                    g_cache[filename] = head, parts, now


def prepare_response(req, resp, head, now):
    resp.etag = head.etag
    expires = next_update_time(now)
    resp.expires = expires  # TODO this doesn't seem to work; need to use
                            # 'cache_expires'
    resp.last_modified = head.modified
    del resp.cache_control
    if head.etag in req.if_none_match:
        logging.info("matched etag, modified %s, expires %s",
                     resp.last_modified, expires)
        resp.status_int = HTTP_NOT_MOD
    elif not req.if_none_match and req.if_modified_since and \
            req.if_modified_since >= resp.last_modified:
        logging.info("not modified since %s, modified %s, expires %s",
                     req.if_modified_since, resp.last_modified, expires)
        resp.status_int = HTTP_NOT_MOD


# Return next exact half hour, i.e. HH:30:00 or HH:00:00
def next_update_time(t):
    r = t.replace(second=0, microsecond=0)
    r += datetime.timedelta(minutes=(30 - (t.minute % 30)))
    return r


def write_response(resp, head, parts):
    logging.info("writing %d-part response, modified %s, expires %s",
                 1 + len(parts), resp.last_modified, resp.expires)
    resp.content_type = 'text/html'
    resp.charset = head.encoding
    resp.write(head.data0)
    for part in parts:
        resp.write(part.data)


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
            raise HTTPInternalServerError()
        parts = ndb.get_multi(keys)
        if any(p.etag != head.etag for p in parts):
            logging.warn("got differing etags, retrying")
        else:
            return sorted(parts, key=lambda p: p.key.string_id())


app = webapp2.WSGIApplication([
    (r'/(?:(.*)\.html)?', PageHandler)
])
