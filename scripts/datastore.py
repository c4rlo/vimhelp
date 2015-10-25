#!/usr/bin/python2 -i

# See
# http://googlecloudplatform.github.io/gcloud-python/stable/datastore-client.html

from gcloud import datastore
import os

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = \
        '/home/carlo/gcloud-vimhelp-hrd.json'
client = datastore.Client(dataset_id='vimhelp-hrd')
