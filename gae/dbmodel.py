from google.appengine.ext import db
from google.appengine.api import namespace_manager
import os

def set_namespace():
    major = os.environ['CURRENT_VERSION_ID'].split('.', 1)[0]
    if major == '1':
        ns = ''
    else:
        ns = 'v' + major
    namespace_manager.set_namespace(ns)

class UnprocessedFile(db.Model):
    url = db.StringProperty()
    data = db.BlobProperty()
    etag = db.BlobProperty()
    encoding = db.StringProperty()

class ProcessedFile(db.Model):
    filename = db.StringProperty()
    data = db.BlobProperty()
    etag = db.BlobProperty()
    encoding = db.StringProperty()
    redo = db.BooleanProperty()

class VimRepositoryInfo(db.Model):
    revision = db.StringProperty()

class MemcacheProcessedFile(object):
    def __init__(self, pf):
        self.data = pf.data
        self.etag = pf.etag
        self.encoding = pf.encoding
