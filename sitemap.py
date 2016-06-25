# Generate 'sitemap.txt' on the fly.

import dbmodel
import operator
import webapp2

BASE_URL = 'http://vimhelp.appspot.com/'

class PageHandler(webapp2.RequestHandler):
    def get(self):
        self.response.content_type = 'text/plain'
        query = dbmodel.ProcessedFileHead.query()
        all_names = \
                query.map(operator.methodcaller('string_id'), keys_only=True)
        self.response.write(BASE_URL + '\n')
        for name in sorted(all_names):
            if name == 'help.txt':
                continue
            self.response.write(BASE_URL + name + '.html\n')


app = webapp2.WSGIApplication([
    (r'/sitemap\.txt', PageHandler)
])
