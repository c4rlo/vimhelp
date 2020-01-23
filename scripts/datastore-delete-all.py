#!/usr/bin/env python3

import os

from google.cloud import datastore

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = \
        '/home/carlo/gcloud-creds/vimhelp2-owner.json'
client = datastore.Client(project='vimhelp2')

KINDS = ('GlobalInfo', 'ProcessedFileHead', 'ProcessedFilePart',
         'RawFileContent', 'RawFileInfo')

for kind in KINDS:
    query = client.query(kind=kind)
    query.keys_only()
    keys = [e.key for e in query.fetch()]
    print(f"Deleting {len(keys)} {kind} entities...")
    client.delete_multi(keys)

print("All done.")
