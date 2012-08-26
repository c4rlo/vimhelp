import sys, os, re, logging, zlib
from dbmodel import ProcessedFile
from google.appengine.api import memcache

def notfound(msg = None):
    logging.info("file not found, msg = " + msg)
    print "Status: 404 Not Found\n"
    print '<p>Not found</p>'
    if msg: print msg
    sys.exit()

def reply(data):
    logging.info("writing response")
    sys.stdout.write(zlib.decompress(data))

FILENAME_RE = re.compile(r"/((?:.*?\.txt|tags)\.html)$")

def main():
    path_info = os.environ['PATH_INFO']
    if path_info == '/':
        filename = 'help.txt.html'
    else:
        m = FILENAME_RE.match(path_info)
        if not m: notfound("illegal url")
        filename = m.group(1)

    cached = memcache.get(filename)
    if cached is not None:
        reply(cached)
    else:
        record = ProcessedFile.all().filter('filename =', filename).get()
        if record is None: notfound("not in database")
        memcache.set(filename, record.data)
        reply(record.data)

if __name__ == '__main__':
    main()
