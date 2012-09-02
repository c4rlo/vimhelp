import logging, zlib, re
import webapp2
from webob.exc import HTTPNotFound
from google.appengine.api import memcache
from dbmodel import *

class PageHandler(webapp2.RequestHandler):
    def get(self, filename):
        if not filename: filename = 'help.txt.html'
        cached = memcache.get(filename)
        if cached is not None:
            self._reply(cached, " (from memcache)")
        else:
            record = ProcessedFile.all().filter('filename =', filename).get()
            if record is not None:
                cached = MemcacheProcessedFile(record)
                memcache.set(filename, cached)
                self._reply(cached)
            else:
                return HTTPNotFound()

    def _reply(self, item, msg_extra = ""):
        self.response.etag = item.etag
        if item.expires:
            self.response.expires = item.expires
        del self.response.cache_control
        if item.etag in webapp2.get_request().if_none_match:
            logging.info("etag %s matched%s", item.etag, msg_extra)
            self.response.status = 304
        else:
            logging.info("writing response%s", msg_extra)
            self.response.content_type = 'text/html'
            self.response.charset = item.encoding.encode()  # unicode -> str
            self.response.write(zlib.decompress(item.data))


app = webapp2.WSGIApplication([
    (r'/((?:.*?\.txt|tags)\.html)?', PageHandler)
])
