import logging, zlib, re
import webapp2
from webob.exc import HTTPNotFound
from google.appengine.api import memcache
from dbmodel import *

HEADERS_CHARSET_RE = re.compile(r'Content-Type: text/html; charset=(.+)$')

class PageHandler(webapp2.RequestHandler):
    def get(self, filename):
        if not filename: filename = 'help.txt.html'
        cached = memcache.get(filename)
        if cached is not None:
            self._reply(cached, " (from memcache)")
        else:
            record = ProcessedFile.all().filter('filename =', filename).get()
            if record is not None:
                if record.encoding is not None:
                    logging.info("got new-style record")
                    cached = MemcacheProcessedFile(record)
                    memcache.set(filename, cached)
                else:
                    logging.info("got old-style record")
                    # support old-style records, but don't memcache them
                    cached = record.data
                self._reply(cached)
            else:
                return HTTPNotFound()

    def _reply(self, item, msg_extra = ""):
        if isinstance(item, MemcacheProcessedFile):
            self.response.etag = item.etag
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
        else:
            # old-style item
            logging.info("writing old-style response%s", msg_extra)
            data = zlib.decompress(item)
            headers, body = data.split('\n\n', 1)
            charset = HEADERS_CHARSET_RE.match(headers).group(1)
            logging.info("charset: %s", charset)
            self.response.content_type = 'text/html'
            self.response.charset = charset
            self.response.write(body)


app = webapp2.WSGIApplication([
    (r'/((?:.*?\.txt|tags)\.html)?', PageHandler)
])
