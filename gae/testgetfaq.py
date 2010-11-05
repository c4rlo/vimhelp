import os, sys, logging, urllib
from google.appengine.api import urlfetch

FAQ_URL = 'https://github.com/chrisbra/vim_faq/raw/master/doc/vim_faq.txt'

etag = urllib.unquote_plus(os.environ.get('QUERY_STRING'))

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

print "Content-Type: text/html\n"

headers = { 'Cache-Control': 'max-age=300' }
if etag:
    print "<p>Using etag: " + etag + "</p>"
    headers['If-None-Match'] = etag
else:
    print "<p>Not using an etag</p>"

result = urlfetch.fetch(FAQ_URL, headers = headers)

if result.status_code == 304:
    print "<p>Page is unchanged (HTTP status 304)</p>"
elif result.status_code != 200:
    log_error("bad HTTP response %d when fetching url %s",
	    result.status_code, FAQ_URL)
    sys.exit()

print "<p>Result headers:</p><pre>" + str(result.headers) + "</pre>"

print "<p>Result:</p><pre>" + result.content + "</pre>"

