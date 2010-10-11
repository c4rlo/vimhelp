from google.appengine.ext import db

class UnprocessedFile(db.Model):
    url = db.StringProperty()
    data = db.BlobProperty()
    etag = db.BlobProperty()

class ProcessedFile(db.Model):
    filename = db.StringProperty()
    data = db.BlobProperty()

