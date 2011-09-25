from google.appengine.ext import db

class UnprocessedFile(db.Model):
    url = db.StringProperty()
    data = db.BlobProperty()
    etag = db.BlobProperty()
    encoding = db.StringProperty()

class ProcessedFile(db.Model):
    filename = db.StringProperty()
    data = db.BlobProperty()
    redo = db.BooleanProperty()

class VimRepositoryInfo(db.Model):
    revision = db.StringProperty()
