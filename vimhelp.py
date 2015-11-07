# Retrieve a help page from the data store, and present to the user

import logging, re, datetime
import webapp2
from webob.exc import HTTPNotFound, HTTPInternalServerError
from dbmodel import *

HTTP_NOT_MOD = 304

class PageHandler(webapp2.RequestHandler):
    def get(self, filename):
        if not filename: filename = 'help.txt'
        # TODO: we should probably set up an url redirect from '/help.txt.html'
        # to just '/', and change the html generator to use that. Also remove
        # 'help.txt.html' from the sitemap.
        head = ProcessedFileHead.get_by_id(filename)
        if not head:
            logging.warn("%s not found in db", filename)
            raise HTTPNotFound()
        req = self.request
        resp = self.response
        resp.etag = head.etag
        # set expires to next exact half hour, i.e. :30:00 or :00:00
        # TODO: race condition if it's now :30:01 and new version is in the
        # process of being generated
        expires = datetime.datetime.utcnow().replace(second=0, microsecond=0)
        expires += datetime.timedelta(minutes=(30 - (expires.minute % 30)))
        resp.expires = expires  # TODO this doesn't seem to work; need to use
                                # 'cache_expires'
        resp.last_modified = head.modified
        del resp.cache_control
        if head.etag in req.if_none_match:
            logging.info("matched etag, modified %s, expires %s",
                         resp.last_modified, expires)
            resp.status = HTTP_NOT_MOD
        elif not req.if_none_match and req.if_modified_since and \
                req.if_modified_since >= resp.last_modified:
            logging.info("not modified since %s, modified %s, expires %s",
                         req.if_modified_since, resp.last_modified, expires)
            resp.status = HTTP_NOT_MOD
        else:
            parts = get_parts(head)
            logging.info("writing %d-part response, modified %s, expires %s",
                         1 + len(parts), resp.last_modified, expires)
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
    if head.numparts == 1: return []
    logging.info("retrieving %d extra part(s)", head.numparts - 1)
    filename = head.key.string_id()
    keys = [ ndb.Key('ProcessedFilePart', filename + ':' + str(i))
                for i in xrange(1, head.numparts) ]
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
    (r'/(?:(.*?\.txt|tags)\.html)?', PageHandler)
])
