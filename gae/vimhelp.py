import logging, re, zlib, datetime
import webapp2
from webob.exc import HTTPNotFound
from google.appengine.api import memcache, taskqueue
from dbmodel import *

HTTP_NOT_MOD = 304

class PageHandler(webapp2.RequestHandler):
    def get(self, filename):
        if not filename: filename = 'help.txt'
        ok = self._reply_from_memcache(filename)
        if ok: return
        ok = self._reply_from_db(filename)
        if not ok: return HTTPNotFound()
        logging.info("enqueueing memcache add")
        try:
            taskqueue.add(queue_name='memcache', url='/memcache_add',
                          params={ 'filename': filename })
        except:
            logging.exception("caught exception")

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
            logging.info("matched etag, modified %s, expires %s, from %s",
                         resp.last_modified, expires, srcname)
            resp.status = HTTP_NOT_MOD
        elif not req.if_none_match and req.if_modified_since and \
                req.if_modified_since >= resp.last_modified:
            logging.info("not modified since %s, modified %s, expires %s," \
                         " from %s", req.if_modified_since, resp.last_modified,
                         expires, srcname)
            resp.status = HTTP_NOT_MOD
        else:
            logging.info("writing %d-part response, modified %s, expires %s," \
                         " from %s", 1 + len(parts), resp.last_modified,
                         expires, srcname)
            resp.content_type = 'text/html'
            resp.charset = head.encoding
            resp.write(head.data0)
            for part in parts:
                resp.write(part.data)

class MemcacheAddHandler(webapp2.RequestHandler):
    def post(self):
        try:
            filename = self.request.get('filename')
            logging.info("attempting to add %s to memcache", filename)
            result = get_from_db(filename)
            if not result: return
            head, parts = result
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
