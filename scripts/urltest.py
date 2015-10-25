import logging
import webapp2
from google.appengine.api import urlfetch

URL = 'https://raw.githubusercontent.com/chrisbra/vim_faq/master/doc/vim_faq.txt'

class UrltestHandler(webapp2.RequestHandler):
    def get(self):
        logging.info("urltest handler")
        headers = { 'If-None-Match': '"ec5ce51ad1b47bb96c63b7b63947ec2d56f4509e"' }
        response = urlfetch.fetch(URL, headers=headers)
        logging.info("response status: %d", response.status_code)
        logging.debug("response headers: %s", response.headers)
        if 'ETag' in response.headers:
            logging.info("Response ETag: %s", response.headers['ETag'])
        else:
            logging.info("No response ETag")

app = webapp2.WSGIApplication([
    ('/urltest', UrltestHandler),
])
