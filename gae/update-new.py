import os, re, datetime, logging, hashlib, base64
import threading
import webapp2
from google.appengine.api import urlfetch, memcache
from google.appengine.ext import db
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
        self._tags_rfi = None
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

        try:
            _update(self, query_string)
        except Exception as e:
            logging.error("%s", e)
        finally:
            # it's important we always remove the log handler, otherwise it will
            # be in place for other requests, including to vimhelp.py, where
            # class HtmlLogFormatter won't exist
            if html_logging:
                logging.getLogger().removeHandler(htmlLogHandler)
            for thr in self._bg_threads: thr.join()

    def _update(self, query_string):
        force = 'force' in query_string
        expm = EXPIRYMINS_RE.match(query_string)
        self._expires = datetime.datetime.now() + \
                datetime.timedelta(minutes=int(expm.group(1))) if expm else None

        self.response.write("<html><body>")

        logging.info("starting update")

        write_redo_flags = None
        if force:
            rfi = RawFileInfo.all().fetch(None)
            for r in rfi: r.redo = True
            write_redo_flags = db.put_async(rfi)

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
            # already have rfi
        elif index_changed:
            rfi = RawFileInfo.get_by_key_name([ m.group(1) for m in
                                               ITEM_RE.finditer(index_html) ]) \
                    or ()
        else:
            rfi = ()

        # when we iterate over the rfi:
        # - make sure this includes the FAQ
        # - exclude the tags, since these are handled specially
        def gen_rfi():
            got_faq = False
            for r in rfi:
                key_name = r.key().name()
                if key_name == TAGS_NAME:
                    self._tags_rfi = r
                else:
                    if key_name == FAQ_NAME:
                        got_faq = True
                    yield r
            if not got_faq:
                faq_r = RawFileInfo.get_by_key_name(FAQ_NAME) or \
                        RawFileInfo(key_name=FAQ_NAME)
                yield faq_r

        urlfetches = []
        for r in gen_rfi():
            rpc = self._make_urlfetch_rpc(r, _make_urlfetch_callback)
            urlfetches.append(rpc)

        if index_changed:
            resp = self._sync_urlfetch(HGTAGS_URL, g.hgtags_etag)
            if resp.status_code == 200:
                data = resp.contents
                end = next(data.rindex('\n', 0, i)
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

    def _make_urlfetch_rpc(self, rfi, make_callback):
        rpc = urlfetch.create_rpc()
        rpc.callback = make_callback(self, rfi, rpc)
        headers = { }
        if rfi.etag: headers['If-None-Match'] = rfi.etag
        urlfetch.make_fetch_call(rpc, **self._urlfetch_args(rfi))
        return rpc

    def _make_urlfetch_callback(self, rfi, rpc):
        return lambda: self._process_and_put(self, rfi, rpc.get_result())

    def _process_and_put(self, rfi, result, need_h2h=True):
        filename = rfi.key().name()
        if result.status_code == 200:
            rfi.redo = False
            rfi.etag = result.headers.get(HTTP_HDR_ETAG)
            rfd = RawFileData(key_name=filename, data=result.content)
            try:
                result.content.decode('UTF-8')
            except UnicodeError:
                rfd.encoding = 'ISO-8859-1'
            else:
                rfd.encoding = 'UTF-8'
            ents = [ rfi, rfd ]
            pfs = self._process(filename, rfd)
            ents.extend(pfs)
            self._put_transactional_async(ents)
        elif rfi.etag and result.status_code == 304:
            if rfi.redo or \
               (filename == HELP_NAME and self._is_new_vim_version):
                rfi.redo = False
                rfd = RawFileData.get_by_key_name(filename)
                # TODO check for rfd is None
                ents = [ rfi ]
                pfs = self._process(filename, rfd)
                self._put_transactional_async(ents)
            elif need_h2h and filename == TAGS_NAME:
                rfd = RawFileData.get_by_key_name(filename)
                # TODO check for rfd is None
                self._get_h2h(rfd)
        else:
            logging.error("urlfetch error for %s: status %d", filename,
                          result.status_code)
            # TODO handle error

    def _process(self, filename, rfd):
        h2h = self._get_h2h(rfd)
        filename = rfd.key().name()
        if filename == FAQ_NAME:
            h2h.add_tags(filename, rfd.data)
        html = h2h.to_html(filename, rfd.data)
        sha1 = hashlib.sha1()
        sha1.update(html)
        etag = base64.b64encode(sha1.digest())
        datalen = len(html)
        pfi = ProcessedFileHead(key_name=filename, encoding=rfd.encoding,
                                expires=self._expires, etag=etag)
        result = [ pfi ]
        if datalen > PFD_MAX_PART_LEN:
            for i in xrange(0, datalen, PFD_MAX_PART_LEN):
                part = html[i:(i+PFD_MAX_PART_LEN)]
                if i == 0:
                    pfi.data0 = part
                else:
                    pfd.append(ProcessedFileDataPart(key_name=filename,
                                                     data=part))
        else:
            pfi.data0 = html
        return result
        # TODO memcache

    def _get_h2h(self, rfd):
        if self._h2h is None:
            if rfd.key().name() == TAGS_NAME:
                self._h2h = VimH2H(rfd.data, self._vim_version)
            else:
                self._process_tags(need_h2h=True)
        return self._h2h

    def _process_tags(self, need_h2h):
        if not self._tags_rfi:
            self._tags_rfi = RawFileInfo.get_by_key_name(TAGS_NAME) \
                    or RawFileInfo(key_name=TAGS_NAME)
        result = urlfetch.fetch(**self._urlfetch_args(self._tags_rfi))
        self._process_and_put(self._tags_rfi, result, need_h2h)

    @classmethod
    def _urlfetch_args(cls, rfi):
        headers = { }
        if rfi.etag:
            headers[HTTP_HDR_IF_NONE_MATCH] = rfi.etag
        return { 'url':     cls._filename_to_url(rfi.key().name()),
                 'headers': headers }

    def _sync_urlfetch(url, etag):
        headers = { }
        if etag:
            headers[HTTP_HDR_IF_NONE_MATCH] = rfi.etag
        return urlfetch.fetch(url, headers)

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
