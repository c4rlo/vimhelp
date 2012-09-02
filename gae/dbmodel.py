from google.appengine.ext import db

class UnprocessedFile(db.Model):
    url = db.StringProperty()
    data = db.BlobProperty()
    encoding = db.StringProperty()
    etag = db.BlobProperty()

class ProcessedFile(db.Model):
    filename = db.StringProperty()
    data = db.BlobProperty()
    encoding = db.StringProperty()
    etag = db.BlobProperty()
    expires = db.DateTimeProperty()
    redo = db.BooleanProperty()

class VimRepositoryInfo(db.Model):
    revision = db.StringProperty()

class MemcacheProcessedFile(object):
    def __init__(self, pf):
        self.data = pf.data
        self.etag = pf.etag
        self.encoding = pf.encoding
        self.expires = pf.expires
