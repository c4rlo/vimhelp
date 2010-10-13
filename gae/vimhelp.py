import sys, os, re, logging, bz2
from dbmodel import ProcessedFile
from google.appengine.api import memcache

def notfound(msg = None):
    logging.info("file not found, msg = " + msg)
    print "Status: 404 Not Found"
    print 'Content-Type: text/html\n'
    print '<p>Not found</p>'
    if msg: print msg
    sys.exit()

path_info = os.environ['PATH_INFO']
if path_info == '/':
    filename = 'index.html'
else:
    m = re.match(r"/((?:.*?\.txt|tags)\.html)$", path_info)
    if not m: notfound("illegal url")
    filename = m.group(1)

cached = memcache.get(filename)
if cached is not None:
    print 'Content-Type: text/html\n'
    print bz2.decompress(cached)
else:
    record = ProcessedFile.all().filter('filename =', filename).get()
    if record is None: notfound("not in database")
    memcache.set(filename, record.data)
    print 'Content-Type: text/html\n'
    print bz2.decompress(record.data)

