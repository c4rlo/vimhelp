import os, re, sys, logging, zlib, hashlib, base64
from dbmodel import *
from google.appengine.api import urlfetch, memcache
from google.appengine.ext import db
from vimh2h import VimH2H

# Once we have consumed about 30 seconds of CPU time, Google will throw us a
# DeadlineExceededError and our script terminates. Therefore, we must be careful
# with the order of operations, to ensure that after this has happened, the next
# scheduled run of the script can pick up where the previous one was
# interrupted.

BASE_URL = 'http://vim.googlecode.com/hg/runtime/doc/'
TAGS_NAME = 'tags'
FAQ_BASE_URL = 'https://raw.github.com/chrisbra/vim_faq/master/doc/'
FAQ_NAME = 'vim_faq.txt'

def main():
    is_dev = (os.environ.get('SERVER_NAME') == 'localhost')
    query_string = os.environ.get('QUERY_STRING', '')
    force = ('force' in query_string)
    debuglog = ('debug' in query_string)

    set_namespace()

    # Set up logging

    if is_dev: logging.getLogger().setLevel(logging.DEBUG)

    htmlLogHandler = logging.StreamHandler(sys.stdout)
    htmlLogHandler.setLevel(logging.DEBUG if debuglog else logging.INFO)
    htmlLogHandler.setFormatter(HtmlLogFormatter())

    logging.getLogger().addHandler(htmlLogHandler)

    print "Content-Type: text/html\n"
    print "<html><body>"

    logging.info("starting update")

    index = fetch(BASE_URL).content()

    skip_help = False

    m = re.search('<title>Revision (.+?): /runtime/doc</title>', index)
    if m:
        rev = m.group(1)
        dbreposi = VimRepositoryInfo.all().get()
        if dbreposi is not None:
            if dbreposi.revision == rev:
                if not force:
                    logging.info("revision %s unchanged, nothing to do (except for faq)", rev)
                    dbreposi = None
                    skip_help = True
                else:
                    logging.info("revision %s unchanged, continuing anyway", rev)
                    dbreposi.delete()
                    dbreposi = VimRepositoryInfo(revision = rev)
            else:
                logging.info("new revision %s (old %s)", rev, dbreposi.revision)
                dbreposi.revision = rev
        else:
            logging.info("encountered revision %s, none in db", rev)
            dbreposi = VimRepositoryInfo(revision = rev)
    else:
        logging.warning("revision not found in index page")

    proc = Processor(redo=force)

    logging.debug("processing files")

    filenames = set()

    if not skip_help:
        for match in re.finditer(r'[^-\w]([-\w]+\.txt|tags)[^-\w]', index):
            filename = match.group(1)
            if filename not in filenames:
                filenames.add(filename)
                proc.process(BASE_URL, filename)

    if dbreposi is not None: dbreposi.put()

    proc.process(FAQ_BASE_URL, FAQ_NAME, add_tags=True)

    logging.info("finished update")
    print "</body></html>"
    logging.getLogger().removeHandler(htmlLogHandler)

class Processor(object):
    def __init__(self, redo):
        self._pfs = { }
        logging.debug("getting processed files")
        for pf in ProcessedFile.all():
            if redo: pf.redo = True
            self._pfs[pf.filename] = pf
        if redo:
            logging.debug("setting redo flag on all processed files")
            db.put(self._pfs.itervalues())
        self._h2h = None

    def process(self, base_url, filename, add_tags=False):
        # Only write back to datastore once we're done
        f = fetch(base_url + filename, write_to_db=False)
        if f is None: return
        filenamehtml = filename + '.html'
        pf = self._pfs.get(filenamehtml)
        if pf is None or pf.redo or f.modified:
            h2h = self._get_h2h()
            if add_tags:
                logging.debug("adding tags for %s", filename)
                h2h.add_tags(filename, f.content())
            html = h2h.to_html(filename, f.content())
            if pf is None:
                pf = ProcessedFile(filename = filenamehtml)
            compressed = zlib.compress(html, 1)
            pf.data = compressed
            pf.encoding = f.encoding()
            pf.redo = False
            sha1 = hashlib.sha1()
            sha1.update(pf.encoding)
            sha1.update(pf.data)
            pf.etag = base64.b64encode(sha1.digest())
            memcache.set(filenamehtml, MemcacheProcessedFile(pf))
            pf.put()
            logging.info("processed %s", filenamehtml)
        else:
            logging.info("%s is unchanged", filename)
        f.write_to_db()

    def _get_h2h(self):
        if self._h2h is None:
            tags = fetch(BASE_URL + TAGS_NAME)
            self._h2h = VimH2H(tags.content())
            logging.info("processed tags file")
        return self._h2h

def fetch(url, write_to_db=True, use_etag=True):
    headers = { }
    dbrecord = UnprocessedFile.all().filter('url =', url).get() or \
            UnprocessedFile(url = url)
    if not dbrecord.etag: use_etag = False
    if use_etag:
        headers['If-None-Match'] = dbrecord.etag
        logging.debug("for %s, saved etag is %s", url, dbrecord.etag)
    result = urlfetch.fetch(url, headers = headers, deadline = 10)
    if use_etag and result.status_code == 304:
	logging.debug("url %s is unchanged", url)
	return FileFromServer(dbrecord, False)
    elif result.status_code != 200:
	logging.error("bad HTTP response %d when fetching url %s",
		result.status_code, url)
	return None
    dbrecord.data = result.content
    dbrecord.etag = result.headers.get('ETag')
    dbrecord.encoding = "UTF-8"
    try:
        result.content.decode("UTF-8")
    except UnicodeError:
        dbrecord.encoding = "ISO-8859-1"
    if write_to_db:
	dbrecord.put()
        logging.debug("fetched %s and written to db", url)
    else:
        logging.debug("fetched %s, not written to db", url)
    return FileFromServer(dbrecord, True)

class FileFromServer(object):
    def __init__(self, upf, modified):
	self.upf = upf
	self.modified = modified

    def content(self): return self.upf.data

    def encoding(self):
        # encode the _name_ of the encoding, i.e.
        # unicode('UTF-8') -> str('UTF-8')
        return self.upf.encoding.encode()

    def write_to_db(self):
	if self.upf is not None: self.upf.put()

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

if __name__ == '__main__':
    main()
