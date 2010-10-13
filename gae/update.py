import os
import re
import sys
import logging
import bz2
from dbmodel import UnprocessedFile, ProcessedFile
from google.appengine.api import urlfetch, memcache
from vimh2h import VimH2H

BASEURL = 'http://vim.googlecode.com/hg/runtime/doc/'
TAGSURL = BASEURL + 'tags'

is_dev = (os.environ.get('SERVER_NAME') == 'localhost')

if is_dev:
    logging.getLogger().setLevel(logging.DEBUG)

class FileFromServer:
    def __init__(self, content, modified):
	self.content = content
	self.modified = modified

def fetch(url):
    dbrecord = UnprocessedFile.all().filter('url =', url).get()
    headers = { }
    if dbrecord is not None and dbrecord.etag is not None:
	headers['If-None-Match'] = dbrecord.etag
    result = urlfetch.fetch(url, headers = headers, deadline = 10)
    if result.status_code == 304 and dbrecord is not None:
	logging.debug("url %s is unchanged", url)
	return FileFromServer(dbrecord.data, False)
    elif result.status_code != 200:
	logging.error("bad HTTP response %d when fetching url %s",
		result.status_code, url)
	sys.exit()
    if dbrecord is None:
	dbrecord = UnprocessedFile(url = url, data = result.content)
    dbrecord.etag = result.headers.get('ETag')
    dbrecord.put()
    logging.debug("fetched %s", url)
    return FileFromServer(result.content, True)

def store(filename, content, pf):
    if pf is None:
	pf = ProcessedFile(filename = filename)
    compressed = bz2.compress(content)
    pf.data = compressed
    pf.put()
    memcache.set(filename, compressed)
    print "<p>Processed file", filename, "</p>"
    logging.debug("Processed file " + filename)

logging.info("starting update")

index = fetch(BASEURL).content
# Note, in theory we can exit right here if index is unchanged, since it
# contains the Mercurial revision id in the title. However, let's not rely on
# that (we already rely on too many things :-)

tags = fetch(TAGSURL).content

h2h = VimH2H(tags)

logging.debug("processed tags")

pfs = { }
for pf in ProcessedFile.all():
    pfs[pf.filename] = pf

filenames = set()

print "Content-Type: text/html\n"

count = 0

for match in re.finditer(r'[^-\w]([-\w]+\.txt|tags)[^-\w]', index):
    filename = match.group(1)
    if filename in filenames: continue
    filenames.add(filename)
    count += 1
    if is_dev and count < 15: continue
    if is_dev and count > 35: break
    f = fetch(BASEURL + filename)
    filenamehtml = filename + '.html'
    pf = pfs.get(filenamehtml)
    if filename == 'help.txt':
	pf2 = pfs.get('index.html')
	if not f.modified and pf is not None and pf2 is not None:
	    print "<p>File", filename, "is unchanged</p>"
	    continue
	html, startpage_html = h2h.to_html(filename, f.content, True)
	store(filenamehtml, html, pf)
	store('index.html', startpage_html, pf2)
    else:
	if not f.modified and pf is not None:
	    print "<p>File", filename, "is unchanged</p>"
	    continue
	html = h2h.to_html(filename, f.content)
	store(filenamehtml, html, pf)

logging.info("finished update")

