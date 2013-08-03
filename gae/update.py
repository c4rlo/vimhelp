# Regularly scheduled update: check which files need updating and process them

import os, re, logging, hashlib, base64, threading
from datetime import datetime
import webapp2
from google.appengine.api import urlfetch, memcache, taskqueue
from google.appengine.ext import db
from dbmodel import *
from vimh2h import VimH2H
from google.appengine.api.urlfetch import DownloadError, ResponseTooLargeError

# Once we have consumed about ten minutes of CPU time, Google will throw us a
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

REVISION_RE = re.compile(r'<title>Revision (.+?): /runtime/doc</title>')
ITEM_RE = re.compile(r'[^-\w]([-\w]+\.txt|tags)[^-\w]')
HGTAG_RE = re.compile(r'^[0-9A-Fa-f]+ v(\d[\w.-]*)$')

PFD_MAX_PART_LEN = 995000

# Request header name
HTTP_HDR_IF_NONE_MATCH = 'If-None-Match'

# Response header name
HTTP_HDR_ETAG = 'ETag'

# HTTP Status
HTTP_OK = 200
HTTP_NOT_MOD = 304

class UpdateHandler(webapp2.RequestHandler):
    def __init__(self, request, response):
        self.initialize(request, response)
        self._save_threads = []
        self._tags_rinfo = None
        self._h2h = None
        self._vim_version = None
        self._is_new_vim_version = False

    def post(self):
        return self._run(self.request.body, html_logging=False)

    def get(self):
        return self._run(self.request.query_string, html_logging=True)

    def _run(self, query_string, html_logging):
        logger = logging.getLogger()
        debuglog = ('debug' in query_string)
        is_dev = (os.environ.get('SERVER_NAME') == 'localhost')
        if debuglog or is_dev: logger.setLevel(logging.DEBUG)

        if html_logging:
            htmlLogHandler = logging.StreamHandler(self.response)
            htmlLogHandler.setFormatter(HtmlLogFormatter())
            if not debuglog:
                htmlLogHandler.setLevel(logging.INFO)
            logger.addHandler(htmlLogHandler)

        try:
            self._update(query_string)
        except:
            logging.exception("exception caught")
            # TODO set bad HTTP status code so the job gets retried?
        finally:
            # it's important we always remove the log handler, otherwise it will
            # be in place for other requests, including to vimhelp.py, where
            # class HtmlLogFormatter won't exist
            if html_logging:
                logging.getLogger().removeHandler(htmlLogHandler)

    def _update(self, query_string):
        force = 'force' in query_string

        self.response.write("<html><body>")

        logging.info("starting %supdate", 'forced ' if force else '')

        if force:
            rfis = RawFileInfo.all().fetch(None)
            for r in rfis: r.redo = True
            db.put(rfis)
            db.delete(db.Key.from_path('GlobalInfo', 'global'))
            logging.info("set redo flag on %d items", len(rfis))

        g = GlobalInfo.get_by_key_name('global') or \
                GlobalInfo(key_name='global')
        g_changed = False  # track any changes we make to 'g'

        logging.debug("global info: %s",
                      ", ".join("{} = {}".format(n, getattr(g, n)) for n in
                                g.properties().iterkeys()))

        # Start by getting the index page of the 'runtime/doc/' directory in the
        # remote Mercurial repository for Vim

        index_etag = g.index_etag
        resp = self._sync_urlfetch(BASE_URL, index_etag)

        if index_etag and resp.status_code == HTTP_NOT_MOD:
            logging.info("index page not modified")
            index_changed = False
        elif resp.status_code == HTTP_OK:
            g_changed = True
            g.index_etag = resp.headers.get(HTTP_HDR_ETAG)
            logging.debug("got index etag %s", g.index_etag)
            index_html = resp.content
            # extract Mercurial revision of this directory from the retrieved
            # HTML page
            hgrev_m = REVISION_RE.search(index_html)
            index_changed = True
            if hgrev_m:
                hgrev_new = hgrev_m.group(1)
                if g.hg_revision == hgrev_new:
                    if force:
                        logging.info("hg revision %s unchanged, continuing " \
                                     "anyway", g.hg_revision)
                    else:
                        logging.info("hg revision %s unchanged", g.hg_revision)
                        index_changed = False
                else:
                    logging.info("new hg revision %s (was: %s)", hgrev_new,
                                 g.hg_revision)
                    g.hg_revision = hgrev_new
            else:
                logging.warn("failed to extract hg revision from index page")
        else:
            raise VimhelpError("bad status %d when getting index page",
                               resp.status_code)

        # Define a generator that we will use to iterate over all 'RawFileInfo'
        # objects that we must process

        def gen_rinfo():
            got_faq = False
            # only need to process any Vim documentation files if the index page
            # has changed
            if index_changed:
                # get all filenames from the index page
                filenames = { m.group(1) for m in ITEM_RE.finditer(index_html) }
                # iterate over all 'RawFileInfo' objects in the data store
                for rinfo in RawFileInfo.all():
                    filename = rinfo.key().name()
                    if filename == FAQ_NAME:
                        logging.debug("found faq in db")
                        got_faq = True
                    elif filename not in filenames:
                        logging.warn("skipping %s: in db but not found on" \
                                     " index page", filename)
                        continue
                    if filename == TAGS_NAME:
                        logging.debug("found tags in db")
                        self._tags_rinfo = rinfo
                    else:
                        logging.info("found %s in db and on index page",
                                      filename)
                        yield rinfo
                    filenames.discard(filename)
                # now iterate over all filenames found in the index page that
                # weren't already in the datastore
                for filename in filenames:
                    logging.info("found %s on index page but not in db",
                                  filename)
                    yield RawFileInfo(key_name=filename)
            if not got_faq:
                # make sure we always process the FAQ, whether the index page
                # changed or not (since it's not part of the Vim documentation)
                faq_rinfo = RawFileInfo.get_by_key_name(FAQ_NAME)
                if faq_rinfo:
                    logging.info("got faq from db")
                else:
                    logging.info("no faq in db, making a new one")
                    faq_rinfo = RawFileInfo(key_name=FAQ_NAME)
                yield faq_rinfo

        # For each file that we want to process, make an async urlfetch call; in
        # the callback, we will process the file.  Note, the callback is not
        # executed asynchronously, but only when we call wait() on the urlfetch
        # object later on.

        def make_urlfetch_callback(rinfo, rpc):
            return lambda: self._process_and_put(rinfo, rpc.get_result())

        urlfetches = []
        for rinfo in gen_rinfo():
            logging.debug("making async urlfetch for %s", rinfo.key().name())
            rpc = urlfetch.create_rpc()
            rpc.callback = make_urlfetch_callback(rinfo, rpc)
            urlfetch.make_fetch_call(rpc, **self._urlfetch_args(rinfo))
            urlfetches.append(rpc)

        # Check if the Vim version has changed; we display it on our front page,
        # so we must keep it updated even if nothing else has changed

        if index_changed:
            resp = self._sync_urlfetch(HGTAGS_URL, g.hgtags_etag)
            if resp.status_code == HTTP_OK:
                data = resp.content
                nlpos = next(data.rfind('\n', 0, i)
                           for i in xrange(len(data), 1, -1)
                           if data[i-1] != '\n')
                if nlpos not in (None, -1):
                    m = HGTAG_RE.match(data[(nlpos + 1):])
                    if m:
                        verspart = m.group(1)
                        if verspart:
                            new_vim_version = verspart.replace('-', '.')
                            if new_vim_version != g.vim_version:
                                logging.info("found new vim version %s"
                                             " (was: %s)", new_vim_version,
                                             g.vim_version)
                                g.vim_version = new_vim_version
                                g.hgtags_etag = resp.headers.get(HTTP_HDR_ETAG)
                                g_changed = True
                                self._is_new_vim_version = True
                            else:
                                logging.info("hgtags file changed but has no"
                                             " new vim version (still %s)",
                                             new_vim_version)
                        else:
                            logging.warn("found blank vim version?!")
                    else:
                        logging.warn("failed to parse vim version in hgtags"
                                     " file")
                else:
                    logging.warn("failed to find last line in hgtags file")
            elif g.hgtags_etag and resp.status_code == HTTP_NOT_MOD:
                logging.info("no new vim version")
            else:
                logging.warn("failed to get hgtags file: HTTP status %d",
                             resp.status_code)

        self._vim_version = g.vim_version

        # Execute the urlfetch callbacks, which will process the results

        for uf in urlfetches:
            try:
                uf.wait()
            except (DownloadError, ResponseTooLargeError) as e:
                logging.error(e)
                # If we could not fetch the URL, continue with the others, but
                # set 'g_changed' to False so we do not save the 'GlobalInfo'
                # object at the end, so that we will retry at the next run
                g_changed = False

        # In case none of the URLs were changed, the tags file has now been
        # completely skipped. Process it now in case it has changed.

        if index_changed and not self._h2h:
            logging.debug("tags file was skipped, processing it now")
            self._process_tags(need_h2h=False)

        # Join the save threads

        if self._save_threads:
            logging.info("joining %d save threads", len(self._save_threads))
            for thr in self._save_threads: thr.join()

        if g_changed:
            logging.info("finished update, writing global info")
            g.put()
        else:
            logging.info("finished update, global info unchanged")

        self.response.write("</body></html>")

    def _process_and_put(self, rinfo, result, need_h2h=True):
        # This is the callback that's invoked when a urlfetch is complete.
        # 'result' is the result of the fetch, and 'rinfo' is the 'RawFileInfo'
        # object for this file (either from the data store or, if it did not
        # exist, newly constructed).
        # We need to process the file and write the result to the data store.
        filename = rinfo.key().name()
        if result.status_code == HTTP_OK:
            # We got a response, process and save it
            rinfo.redo = False
            rinfo.etag = result.headers.get(HTTP_HDR_ETAG)
            rdata = RawFileData(key_name=filename, data=result.content)
            try:
                result.content.decode('UTF-8')
            except UnicodeError:
                rdata.encoding = 'ISO-8859-1'
            else:
                rdata.encoding = 'UTF-8'
            logging.info("processing new %s, encoding is %s", filename,
                         rdata.encoding)
            phead, ppart = self._process(filename, rdata)
            self._save(rinfo, rdata, phead, ppart)
        elif rinfo.etag and result.status_code == HTTP_NOT_MOD:
            # Based on the ETag we sent, the content of the file is not modified
            if rinfo.redo or \
               (filename == HELP_NAME and self._is_new_vim_version):
                logging.info("%s unchanged, processing it anyway", filename)
                rinfo.redo = False
                rdata = RawFileData.get_by_key_name(filename)
                if rdata:
                    phead, ppart = self._process(filename, rdata)
                    self._save(rinfo, None, phead, ppart)
                else:
                    logging.error("data not in db!")
            elif need_h2h and filename == TAGS_NAME:
                logging.info("tags unchanged, using existing version")
                rdata = RawFileData.get_by_key_name(filename)
                if rdata:
                    self._get_h2h(rdata)
                else:
                    logging.error("tags data not in db!")
            else:
                logging.info("%s unchanged", filename)
        else:
            logging.error("urlfetch error for %s: status %d", filename,
                          result.status_code)

    def _process(self, filename, rdata):
        # Generate the HTML version of a documentation file
        h2h = self._get_h2h(rdata)
        filename = rdata.key().name()
        if filename == FAQ_NAME:
            logging.debug("adding tags for faq")
            h2h.add_tags(filename, rdata.data)
        html = h2h.to_html(filename, rdata.data, rdata.encoding)
        # TODO: instead of the SHA1, the timestamp should be enough
        sha1 = hashlib.sha1()
        sha1.update(html)
        etag = base64.b64encode(sha1.digest())
        datalen = len(html)
        phead = ProcessedFileHead(key_name=filename, encoding=rdata.encoding,
                                modified=datetime.utcnow(), etag=etag)
        ppart = [ ]
        if datalen > PFD_MAX_PART_LEN:
            phead.numparts = 0
            for i in xrange(0, datalen, PFD_MAX_PART_LEN):
                part = html[i:(i+PFD_MAX_PART_LEN)]
                if i == 0:
                    phead.data0 = part
                else:
                    partname = filename + ':' + str(phead.numparts)
                    ppart.append(ProcessedFilePart(key_name=partname,
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
                logging.debug("constructed VimH2H object")
            else:
                logging.debug("processing tags in order to construct VimH2H" \
                              " object")
                self._process_tags(need_h2h=True)
        return self._h2h

    def _process_tags(self, need_h2h):
        if not self._tags_rinfo:
            self._tags_rinfo = RawFileInfo.get_by_key_name(TAGS_NAME) \
                    or RawFileInfo(key_name=TAGS_NAME)
        result = urlfetch.fetch(**self._urlfetch_args(self._tags_rinfo))
        self._process_and_put(self._tags_rinfo, result, need_h2h)

    def _save(self, rinfo, rdata, phead, ppart):
        # Save a processed file to the datastore and memcache. We do this in a
        # new thread so that we don't block the caller on the I/O.

        @db.transactional(xg=True)
        def put_trans(entities):
            db.put(entities)

        def save(rinfo, rdata, phead, ppart):
            # order of statements is important: we might get a deadline exceeded
            # error any time
            filename = phead.key().name()
            logging.debug("saving %s", filename)
            old_genid = rinfo.memcache_genid
            new_genid = 1 - (old_genid or 0)
            # 1. Put processed file
            put_trans([ phead ] + ppart)
            # 2. Put memcache
            # TODO: perhaps only add it if it was already in memcache
            cmap = { memcache_part_name(filename, new_genid, i + 1):
                    MemcachePart(part) for i, part in enumerate(ppart) }
            cmap[filename] = phead
            memcache.set_multi(cmap)
            memcache.set(filename, MemcacheHead(phead, new_genid))
            # 3. Put raw file
            rinfo.memcache_genid = new_genid
            raw = [ rinfo ]
            if rdata: raw.append(rdata)
            put_trans(raw)
            # 4. Clean up memcache
            memcache.delete_multi(
                [ memcache_part_name(filename, old_genid, i + 1) for i in
                 xrange(len(ppart)) ])
            if ppart:
                logging.info("saved %s to db and memcache (%d parts)", filename,
                             1 + len(ppart))
            else:
                logging.info("saved %s to db and memcache", filename)

        logging.debug("starting new thread to save %s", phead.key().name())
        thr = threading.Thread(target=save, args=(rinfo, rdata, phead, ppart))
        thr.start()
        self._save_threads.append(thr)

    @classmethod
    def _urlfetch_args(cls, rinfo):
        headers = { }
        if rinfo.etag:
            headers[HTTP_HDR_IF_NONE_MATCH] = rinfo.etag
        return { 'url':     cls._filename_to_url(rinfo.key().name()),
                 'headers': headers }

    @staticmethod
    def _sync_urlfetch(url, etag):
        headers = { }
        if etag:
            headers[HTTP_HDR_IF_NONE_MATCH] = etag
        return urlfetch.fetch(url, headers=headers)

    @staticmethod
    def _filename_to_url(filename):
        if filename == FAQ_NAME:
            base = FAQ_BASE_URL
        else:
            base = BASE_URL
        return base + filename

class EnqueueUpdateHandler(webapp2.RequestHandler):
    def get(self):
        logging.info("enqueueing update")
        taskqueue.add(queue_name='update', url='/update',
                      payload=self.request.query_string)

class VimhelpError(Exception):
    def __init__(self, msg, *args):
        self.msg = msg
        self.args = args

    def __str__(self):
        return self.msg % args

class HtmlLogFormatter(logging.Formatter):
    def format(self, record):
        fmsg = super(HtmlLogFormatter, self).format(record). \
                replace('&', '&amp;'). \
                replace('<', '&lt;').replace('>', '&gt;'). \
                replace(' ', '&nbsp;<wbr/>').replace('\n', '<br/>')
        if record.levelno >= logging.ERROR:
            fmsg = 'ERROR: ' + fmsg
        if record.levelno >= logging.WARNING:
            return '<p><b>' + fmsg + '</b></p>'
        elif record.levelno >= logging.INFO:
            return '<p>' + fmsg + '</p>'
        else:
            return '<p style="color: gray">' + fmsg + '</p>'

app = webapp2.WSGIApplication([
    ('/update', UpdateHandler),
    ('/enqueue_update', EnqueueUpdateHandler)
])
