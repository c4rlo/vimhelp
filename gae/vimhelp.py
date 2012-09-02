import logging, zlib
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
                if hasattr(record, 'encoding'):
                    cached = MemcacheProcessedFile(record)
                    memcache.set(filename, cached)
                else:
                    # support old-style records, but don't memcache them
                    cached = record.data
                self._reply(cached)
            else:
                return HTTPNotFound()

    def _reply(self, item, msg_extra = ""):
        if hasattr(item, 'encoding'):
            self.response.etag = item.etag
            if item.etag in webapp2.get_request().if_none_match:
                logging.info("etag %s matched%s", item.etag, msg_extra)
                self.response.status = 304
            else:
                logging.info("writing response%s", msg_extra)
                self.response.content_type = 'text/html'
                self.response.charset = item.encoding
                self.response.write(zlib.decompress(item.data))
        else:
            # old-style item
            logging.info("writing old-style response%s", msg_extra)
            self.response.write(zlib.decompress(item))


app = webapp2.WSGIApplication([
    (r'/((?:.*?\.txt|tags)\.html)?', PageHandler)
])
