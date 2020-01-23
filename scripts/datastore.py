#!/usr/bin/env -S python3 -i

# See
# https://googleapis.dev/python/datastore/latest/client.html

import os

from google.cloud import datastore

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = \
        '/home/carlo/gcloud-creds/vimhelp2-owner.json'
client = datastore.Client(project='vimhelp2')
