import logging, re, zlib, datetime
import webapp2
from webob.exc import HTTPNotFound
from google.appengine.api import memcache, taskqueue
from dbmodel import *

TASKNAME_INVALID_CHARS_RE = re.compile(r'[^0-9a-zA-Z_-]')

class PageHandler(webapp2.RequestHandler):
    def get(self, filename):
        if not filename: filename = 'help.txt'
        success = self._reply_from_memcache(filename)
        if success: return
        success = self._reply_from_db(filename)
        if success:
            logging.info("enqueueing memcache add")
            taskqueue.add(queue_name='memcache', url='/memcache_add',
                          params={ 'filename': filename })
            return
        success = self._reply_legacy(filename + '.html')
        if success: return
        return HTTPNotFound()

    def _reply_from_memcache(self, filename):
        head = memcache.get(filename)
        if not head: return False
        parts = []
        for i in xrange(1, head.numparts):
            partname = memcache_part_name(filename, head.genid, i)
            part = memcache.get(partname)
            if not part: return False
            parts.append(part)
        self._reply(head, parts, 'memcache')
        return True

    def _reply_from_db(self, filename):
        result = get_from_db(filename)
        if not result: return False
        head, parts = result
        self._reply(head, parts, 'db')
        return True

    def _reply(self, head, parts, srcname):
        resp = self.response
        resp.etag = head.etag
        if head.expires:
            resp.expires = head.expires
        del resp.cache_control
        if head.etag in self.request.if_none_match:
            logging.info("matched etag (from %s)", srcname)
            resp.status = 304
        else:
            logging.info("writing %d-part response (from %s)",
                         1 + len(parts), srcname)
            resp.content_type = 'text/html'
            resp.charset = head.encoding
            resp.write(head.data0)
            for part in parts:
                resp.write(part.data)

    def _reply_legacy(self, filename):
        item = ProcessedFile.all().filter('filename =', filename).get()
        if not item:
            logging.warn("LEGACY: file %s not found", filename)
            return False
        self.response.etag = item.etag
        if item.expires:
            self.response.expires = item.expires
        del self.response.cache_control
        if item.etag in self.request.if_none_match:
            logging.info("LEGACY: etag matched")
            self.response.status = 304
        else:
            logging.info("LEGACY: writing response")
            self.response.content_type = 'text/html'
            self.response.charset = item.encoding.encode()  # unicode -> str
            self.response.write(zlib.decompress(item.data))
        return True

class MemcacheAddHandler(webapp2.RequestHandler):
    def post(self):
        try:
            filename = self.request.get('filename')
            logging.info("attempting to add %s to memcache", filename)
            result = get_from_db(filename)
            if not result: return
            head, parts = result
            if not head.expires or head.expires < datetime.datetime.now():
                logging.info("expiry (%s) is in the past, bailing out",
                             head.expires)
                return
            if head.numparts == 1:
                memcache.add(filename, MemcacheHead(head, None))
                logging.info("added to memcache (single part)")
            else:
                rinfo = RawFileInfo.get_by_key_name(filename)
                if not rinfo:
                    logging.warn("raw file info not found")
                    return
                genid = rinfo.memcache_genid
                objects = { filename: MemcacheHead(head, genid) }
                for i, part in enumerate(parts):
                    partname = memcache_part_name(filename, genid, i + 1)
                    objects[partname] = part
                memcache.add_multi(objects)
                logging.info("added to memcache (%d parts)", 1 + len(parts))
        except BaseException:
            logging.exception("caught exception")
            # do not return a bad HTTP status code, we do not want this task
            # retried

def get_from_db(filename):
    head = ProcessedFileHead.get_by_key_name(filename)
    if not head:
        logging.warn("%s not found in db", filename)
        return None
    parts = []
    for i in xrange(1, head.numparts):
        partname = filename + ':' + str(i)
        part = ProcessedFilePart.get_by_key_name(partname)
        if not part:
            logging.warn("%s not found in db", partname)
            return None
        parts.append(part)
    return head, parts

app = webapp2.WSGIApplication([
    (r'/(?:(.*?\.txt|tags)\.html)?', PageHandler),
    (r'/memcache_add', MemcacheAddHandler)
])
