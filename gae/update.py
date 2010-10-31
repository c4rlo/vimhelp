import os, re, sys, logging, bz2
from dbmodel import *
from google.appengine.api import urlfetch, memcache
from vimh2h import VimH2H

# Once we have consumed about 30 seconds of CPU time, Google will throw us a
# DeadlineExceededError and our script terminates. Therefore, we must be careful
# with the order of operations, to ensure that after this has happened, the next
# scheduled run of the script can pick up where the previous one was
# interrupted.

BASEURL = 'http://vim.googlecode.com/hg/runtime/doc/'
TAGSURL = BASEURL + 'tags'

is_dev = (os.environ.get('SERVER_NAME') == 'localhost')
force = (os.environ.get('QUERY_STRING') == 'force')

if is_dev:
    logging.getLogger().setLevel(logging.DEBUG)

def do_log(msg, args, logfunc, html_msg = None):
    msg = msg % args
    logfunc(msg)
    if html_msg is None: html_msg = "<p>" + msg + "</p>"
    print html_msg

def log_debug(msg, *args): do_log(msg, args, logging.debug)
def log_info(msg, *args): do_log(msg, args, logging.info)
def log_warning(msg, *args):
    do_log(msg, args, logging.info, "<p><b>" + msg + "</b></p>")
def log_error(msg, *args):
    do_log(msg, args, logging.error, "<h2>" + msg + "</h2>")

class FileFromServer:
    def __init__(self, content, modified, upf):
	self.content = content
	self.modified = modified
	self.upf = upf

    def write_to_cache(self):
	if self.upf is not None: self.upf.put()

def fetch(url, write_to_cache = True):
    dbrecord = UnprocessedFile.all().filter('url =', url).get()
    headers = { }
    if dbrecord is not None and dbrecord.etag is not None:
	logging.debug("for %s, saved etag is %s", url, dbrecord.etag)
	headers['If-None-Match'] = dbrecord.etag
    result = urlfetch.fetch(url, headers = headers, deadline = 10)
    if result.status_code == 304 and dbrecord is not None:
	logging.debug("url %s is unchanged", url)
	return FileFromServer(dbrecord.data, False, None)
    elif result.status_code != 200:
	log_error("bad HTTP response %d when fetching url %s",
		result.status_code, url)
	sys.exit()
    if dbrecord is None:
	dbrecord = UnprocessedFile(url = url)
    dbrecord.data = result.content
    dbrecord.etag = result.headers.get('ETag')
    if write_to_cache:
	dbrecord.put()
    logging.debug("fetched %s", url)
    return FileFromServer(result.content, True, dbrecord)

def store(filename, content, pf):
    if pf is None:
	pf = ProcessedFile(filename = filename)
    compressed = bz2.compress(content)
    pf.data = compressed
    pf.redo = False
    memcache.set(filename, compressed)
    pf.put()
    log_debug("Processed file %s", filename)

index = fetch(BASEURL).content

print "Content-Type: text/html\n"

log_info("starting update")

m = re.search('<title>Revision (.+?): /runtime/doc</title>', index)
if m:
    rev = m.group(1)
    dbreposi = VimRepositoryInfo.all().get()
    if dbreposi is not None:
	if dbreposi.revision == rev:
	    if not force:
		log_info("revision %s unchanged, nothing to do", rev)
		sys.exit()
	    else:
		log_info("revision %s unchanged, continuing anyway", rev)
		dbreposi.delete()
		dbreposi = VimRepositoryInfo(revision = rev)
	else:
	    log_info("new revision %s (old %s)", rev, dbreposi.revision)
	    dbreposi.revision = rev
    else:
	log_info("encountered revision %s, none in db", rev)
	dbreposi = VimRepositoryInfo(revision = rev)
else:
    log_warning("revision not found in index page")

tags = fetch(TAGSURL).content

h2h = VimH2H(tags)

log_debug("processed tags")

pfs = { }
for pf in ProcessedFile.all():
    if force:
	pf.redo = True
	pf.put()
    pfs[pf.filename] = pf

filenames = set()

count = 0

for match in re.finditer(r'[^-\w]([-\w]+\.txt|tags)[^-\w]', index):
    filename = match.group(1)
    if filename in filenames: continue
    filenames.add(filename)
    count += 1
    #if is_dev and count < 15: continue
    #if is_dev and count > 35: break
    f = fetch(BASEURL + filename, False)
    filenamehtml = filename + '.html'
    pf = pfs.get(filenamehtml)
    if pf is None or pf.redo or f.modified:
	html = h2h.to_html(filename, f.content)
	store(filenamehtml, html, pf)
    else:
	print "<p>File", filename, "is unchanged</p>"
    f.write_to_cache()

if dbreposi is not None: dbreposi.put()

log_info("finished update")

