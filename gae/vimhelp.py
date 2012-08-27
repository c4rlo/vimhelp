import sys, os, re, logging, zlib
import webapp2
from webob.exc import HTTPNotFound
from dbmodel import *
from google.appengine.api import memcache

class PageHandler(webapp2.RequestHandler):
    def initialize(self, request, response):
        super(PageHandler, self).initialize(request, response)
        set_namespace()

    def get(self, filename):
        if not filename: filename = 'help.txt.html'
        cached = memcache.get(filename)
        if cached is not None:
            self._reply(cached)
        else:
            record = ProcessedFile.all().filter('filename =', filename).get()
            if record is not None:
                cached = MemcacheProcessedFile(record)
                memcache.set(filename, cached)
                self._reply(cached)
            else:
                return HTTPNotFound()

    def _reply(self, item):
        self.response.etag = item.etag
        if item.etag in webapp2.get_request().if_none_match:
            logging.info("etag %s matched", item.etag)
            self.response.status = 304
        else:
            logging.info("writing response")
            self.response.content_type = 'text/html'
            self.response.charset = item.encoding
            self.response.write(zlib.decompress(item.data))


app = webapp2.WSGIApplication([
    (r'/((?:.*?\.txt|tags)\.html)?', PageHandler)
])
