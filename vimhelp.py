# Retrieve a help page from the data store, and present to the user

import logging, re, datetime
import webapp2
from webob.exc import HTTPNotFound
from dbmodel import *

HTTP_NOT_MOD = 304

class PageHandler(webapp2.RequestHandler):
    def get(self, filename):
        if not filename: filename = 'help.txt'
        # TODO: we should probably set up an url redirect from '/help.txt.html'
        # to just '/', and change the html generator to use that. Also remove
        # 'help.txt.html' from the sitemap.
        result = get_from_db(filename)
        if not result: return HTTPNotFound()
        head, parts = result
        req = self.request
        resp = self.response
        resp.etag = head.etag
        # set expires to next exact half hour, i.e. :30:00 or :00:00
        expires = datetime.datetime.utcnow().replace(second=0, microsecond=0)
        expires += datetime.timedelta(minutes=(30 - (expires.minute % 30)))
        resp.expires = expires
        resp.last_modified = head.modified
        del resp.cache_control
        if head.etag in req.if_none_match:
            logging.info("matched etag, modified %s, expires %s, from db",
                         resp.last_modified, expires)
            resp.status = HTTP_NOT_MOD
        elif not req.if_none_match and req.if_modified_since and \
                req.if_modified_since >= resp.last_modified:
            logging.info("not modified since %s, modified %s, expires %s," \
                         " from db", req.if_modified_since, resp.last_modified,
                         expires)
            resp.status = HTTP_NOT_MOD
        else:
            logging.info("writing %d-part response, modified %s, expires %s," \
                         " from db", 1 + len(parts), resp.last_modified,
                         expires)
            resp.content_type = 'text/html'
            resp.charset = head.encoding
            resp.write(head.data0)
            for part in parts:
                resp.write(part.data)

def get_from_db(filename):
    head = ProcessedFileHead.get_by_id(filename)
    if not head:
        logging.warn("%s not found in db", filename)
        return None
    parts = []
    for i in xrange(1, head.numparts):
        partname = filename + ':' + str(i)
        part = ProcessedFilePart.get_by_id(partname)
        if not part:
            logging.warn("%s not found in db", partname)
            return None
        parts.append(part)
    return head, parts

app = webapp2.WSGIApplication([
    (r'/(?:(.*?\.txt|tags)\.html)?', PageHandler)
])
