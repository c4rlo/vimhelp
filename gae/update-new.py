import os, re, datetime, logging, hashlib, base64
import threading
import webapp2
from google.appengine.api import urlfetch, memcache
from google.appengine.ext import db
from google.appengine.runtime import DeadlineExceededError
from dbmodel import *
from vimh2h import VimH2H

# Once we have consumed about 60 seconds of CPU time, Google will throw us a
# DeadlineExceededError and our script terminates. Therefore, we must be careful
# with the order of operations, to ensure that after this has happened, the next
# scheduled run of the script can pick up where the previous one was
# interrupted.

BASE_URL = 'http://vim.googlecode.com/hg/runtime/doc/'
TAGS_NAME = 'tags'
HGTAGS_URL = 'http://vim.googlecode.com/hg/.hgtags'
FAQ_BASE_URL = 'https://raw.github.com/chrisbra/vim_faq/master/doc/'
FAQ_NAME = 'vim_faq.txt'
HELP_NAME = 'help.txt'

EXPIRYMINS_RE = re.compile(r'expirymins=(\d+)')
REVISION_RE = re.compile(r'<title>Revision (.+?): /runtime/doc</title>')
ITEM_RE = re.compile(r'[^-\w]([-\w]+\.txt|tags)[^-\w]')
HGTAG_RE = re.compile(r'^[0-9A-Fa-f]+ v(\d+-\d+-\d+)$')

PFD_MAX_PART_LEN = 1000000  # bit less than a meg

# Request header name
HTTP_HDR_IF_NONE_MATCH = 'If-None-Match'

# Response header name
HTTP_HDR_ETAG = 'ETag'


class PageHandler(webapp2.RequestHandler):
    def __init__(self):
        self._bg_threads = []
        self._tags_rinfo = None
        self._h2h = None
        self._vim_version = None
        self._is_new_vim_version = False

    def get(self):
        # Set up logging

        query_string = self.request.query_string
        html_logging = ('no_html_log' not in query_string)

        if html_logging:
            debuglog = ('debug' in query_string)
            is_dev = (os.environ.get('SERVER_NAME') == 'localhost')
            if is_dev: logging.getLogger().setLevel(logging.DEBUG)

            htmlLogHandler = logging.StreamHandler(self.response)
            htmlLogHandler.setLevel(logging.DEBUG if debuglog else logging.INFO)
            htmlLogHandler.setFormatter(HtmlLogFormatter())

            logging.getLogger().addHandler(htmlLogHandler)

        deadline_exceeded = False

        try:
            _update(self, query_string)
        except DeadlineExceededError:
            deadline_exceeded = True
        except Exception as e:
            logging.error("%s", e)
        finally:
            # it's important we always remove the log handler, otherwise it will
            # be in place for other requests, including to vimhelp.py, where
            # class HtmlLogFormatter won't exist
            if html_logging:
                logging.getLogger().removeHandler(htmlLogHandler)
            for thr in self._bg_threads: thr.join()
            if deadline_exceeded:
                pass
                # TODO: set expired on all rinfo's we haven't processed yet

    def _update(self, query_string):
        force = 'force' in query_string
        expm = EXPIRYMINS_RE.match(query_string)
        self._expires = datetime.datetime.now() + \
                datetime.timedelta(minutes=int(expm.group(1))) if expm else None

        self.response.write("<html><body>")

        logging.info("starting update")

        write_redo_flags = None
        if force:
            rinfo = RawFileInfo.all().fetch(None)
            for r in rinfo: r.redo = True
            write_redo_flags = db.put_async(rinfo)

        g = GlobalInfo.get_by_key_name('global') or \
                GlobalInfo(key_name='global')
        g_changed = False
        index_changed = False

        resp = self._sync_urlfetch(BASE_URL, g.index_etag)
        if g.index_etag and resp.status_code == 304:  # Not Modified
            pass
        elif resp.status_code == 200:  # OK
            g_changed = True
            g.index_etag = resp.headers.get(HTTP_HDR_ETAG)
            index_html = resp.content
            hgrev_m = REVISION_RE.search(index_html)
            index_changed = True
            if hgrev_m:
                hgrev_new = hgrev_m.group(1)
                if g.hgrev == hgrev_new:
                    index_changed = False
                else:
                    g.hgrev = hgrev_new
        elif g.index_etag:
            # we can still go on: we have the previous etag, which implies that
            # we have at least some of the raw file info in the db
            index_changed = False
            logging.warn("bad status %d when getting index", resp.status_code)
        else:
            raise VimhelpError("bad status %d when getting index",
                               resp.status_code)

        if write_redo_flags:
            write_redo_flags.get_result()
            # already have rinfo
        elif index_changed:
            rinfo = RawFileInfo.get_by_key_name([ m.group(1) for m in
                                               ITEM_RE.finditer(index_html) ]) \
                    or ()
        else:
            rinfo = ()

        # when we iterate over the rinfo:
        # - make sure this includes the FAQ
        # - exclude the tags, since these are handled specially
        def gen_rinfo():
            got_faq = False
            for r in rinfo:
                key_name = r.key().name()
                if key_name == TAGS_NAME:
                    self._tags_rinfo = r
                else:
                    if key_name == FAQ_NAME:
                        got_faq = True
                    yield r
            if not got_faq:
                faq_r = RawFileInfo.get_by_key_name(FAQ_NAME) or \
                        RawFileInfo(key_name=FAQ_NAME)
                yield faq_r

        urlfetches = []
        for r in gen_rinfo():
            rpc = self._make_urlfetch_rpc(r, _make_urlfetch_callback)
            urlfetches.append(rpc)

        if index_changed:
            resp = self._sync_urlfetch(HGTAGS_URL, g.hgtags_etag)
            if resp.status_code == 200:
                data = resp.contents
                nlpos = next(data.rindex('\n', 0, i)
                           for i in xrange(len(data), 1, -1)
                           if data[i-1] != '\n')
                g.vim_version = HGTAG_RE.match(data[(nlpos+1):]). \
                        group(1).replace('-', '.')
                g.hgtags_etag = resp.headers.get(HTTP_HDR_ETAG)
                g_changed = True
                self._is_new_vim_version = True
            elif g.hgtags_etag and resp.status_code == 304:
                pass
            else:
                pass # TODO log error

        self._vim_version = g.vim_version

        # execute the callbacks
        for uf in urlfetches: uf.wait()

        # in case none of the urls were changed, the tags have now been
        # completely skipped. deal with that case.
        if not self._h2h:
            self._process_tags(need_h2h=False)

        if g_changed: g.put()

        logging.info("finished update")
        self.response.write("</body></html>")

    def _make_urlfetch_rpc(self, rinfo, make_callback):
        rpc = urlfetch.create_rpc()
        rpc.callback = make_callback(self, rinfo, rpc)
        headers = { }
        if rinfo.etag: headers['If-None-Match'] = rinfo.etag
        urlfetch.make_fetch_call(rpc, **self._urlfetch_args(rinfo))
        return rpc

    def _make_urlfetch_callback(self, rinfo, rpc):
        return lambda: self._process_and_put(self, rinfo, rpc.get_result())

    def _process_and_put(self, rinfo, result, need_h2h=True):
        filename = rinfo.key().name()
        if result.status_code == 200:
            rinfo.redo = False
            rinfo.etag = result.headers.get(HTTP_HDR_ETAG)
            rdata = RawFileData(key_name=filename, data=result.content)
            try:
                result.content.decode('UTF-8')
            except UnicodeError:
                rdata.encoding = 'ISO-8859-1'
            else:
                rdata.encoding = 'UTF-8'
            phead, ppart = self._process(filename, rdata)
            self._save(rinfo, rdata, phead, ppart)
        elif rinfo.etag and result.status_code == 304:
            if rinfo.redo or \
               (filename == HELP_NAME and self._is_new_vim_version):
                rinfo.redo = False
                rdata = RawFileData.get_by_key_name(filename)
                # TODO check for rdata is None
                phead, ppart = self._process(filename, rdata)
                self._save(rinfo, None, phead, ppart)
            elif need_h2h and filename == TAGS_NAME:
                rdata = RawFileData.get_by_key_name(filename)
                # TODO check for rdata is None
                self._get_h2h(rdata)
        else:
            logging.error("urlfetch error for %s: status %d", filename,
                          result.status_code)
            # TODO handle error

    def _process(self, filename, rdata):
        h2h = self._get_h2h(rdata)
        filename = rdata.key().name()
        if filename == FAQ_NAME:
            h2h.add_tags(filename, rdata.data)
        html = h2h.to_html(filename, rdata.data)
        sha1 = hashlib.sha1()
        sha1.update(html)
        etag = base64.b64encode(sha1.digest())
        datalen = len(html)
        phead = ProcessedFileHead(key_name=filename, encoding=rdata.encoding,
                                expires=self._expires, etag=etag)
        ppart = [ ]
        if datalen > PFD_MAX_PART_LEN:
            for i in xrange(0, datalen, PFD_MAX_PART_LEN):
                part = html[i:(i+PFD_MAX_PART_LEN)]
                if i == 0:
                    phead.data0 = part
                else:
                    ppart.append(ProcessedFilePart(key_name=filename,
                                                     data=part))
                phead.numparts += 1
        else:
            phead.numparts = 1
            phead.data0 = html
        return phead, ppart

    def _get_h2h(self, rdata):
        if self._h2h is None:
            if rdata.key().name() == TAGS_NAME:
                self._h2h = VimH2H(rdata.data, self._vim_version)
            else:
                self._process_tags(need_h2h=True)
        return self._h2h

    def _process_tags(self, need_h2h):
        if not self._tags_rinfo:
            self._tags_rinfo = RawFileInfo.get_by_key_name(TAGS_NAME) \
                    or RawFileInfo(key_name=TAGS_NAME)
        result = urlfetch.fetch(**self._urlfetch_args(self._tags_rinfo))
        self._process_and_put(self._tags_rinfo, result, need_h2h)

    @classmethod
    def _urlfetch_args(cls, rinfo):
        headers = { }
        if rinfo.etag:
            headers[HTTP_HDR_IF_NONE_MATCH] = rinfo.etag
        return { 'url':     cls._filename_to_url(rinfo.key().name()),
                 'headers': headers }

    def _sync_urlfetch(url, etag):
        headers = { }
        if etag:
            headers[HTTP_HDR_IF_NONE_MATCH] = rinfo.etag
        return urlfetch.fetch(url, headers)

    @staticmethod
    def _save(rinfo, rdata, phead, ppart):
        @db.transactional(xg=True)
        def put_trans(entities):
            db.put(entities)
        def save():
            # order of statements is important: we might get a deadline exceeded
            # error any time
            filename = phead.key().name()
            old_genid = rinfo.memcache_genid
            new_genid = 1 - (old_genid or 0)
            # 1. Put processed file
            put_trans([ phead ] + ppart)
            # 2. Put raw file
            rinfo.memcache_genid = new_genid
            raw = [ rinfo ]
            if rdata: raw.append(rdata)
            put_trans(raw)
            # 3. Put memcache
            cmap = { memcache_part_name(filename, new_genid, i + 1):
                    MemcachePart(part) for part, i in enumerate(ppart) }
            cmap[filename] = phead
            memcache.set_multi(cmap)
            # 4. Clean up memcache
            memcache.delete_multi(
                [ memcache_part_name(filename, old_genid, i + 1) for i in
                 xrange(len(ppart)) ])
        thr = threading.Thread(run=save)
        thr.start()
        self_bg_threads.append(thr)

    @staticmethod
    def _put_transactional_async(models):
        @db.transactional
        def do_it():
            for model in models: model.put()
        thr = threading.Thread(run=do_it)
        thr.start()
        self._bg_threads.append(thr)

    @staticmethod
    def _filename_to_url(filename):
        if filename == FAQ_NAME:
            base = FAQ_BASE_URL
        else:
            base = BASE_URL
        return base + filename

class VimhelpError(Exception):
    def __init__(self, msg, *args):
        self.msg = msg
        self.args = args

    def __str__(self):
        return self.msg % args

class HtmlLogFormatter(logging.Formatter):
    def __init__(self):
        return super(HtmlLogFormatter, self).__init__()

    def format(self, record):
        fmsg = super(HtmlLogFormatter, self).format(record)
        if record.levelno >= logging.ERROR:
            return '<h2>' + fmsg + '</h2>'
        elif record.levelno >= logging.WARNING:
            return '<p><b>' + fmsg + '</b></p>'
        elif record.levelno >= logging.INFO:
            return '<p>' + fmsg + '</p>'
        else:
            return '<p style="color: gray">' + fmsg + '</p>'

app = webapp2.WSGIApplication([
    ('/update', UpdateHandler)
])
