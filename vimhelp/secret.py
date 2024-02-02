import json
import os
import threading

import google.cloud.secretmanager


g_secrets = None
g_lock = threading.Lock()


def github_token():
    return _get_secrets()["github_token"]


def admin_password():
    return _get_secrets()["admin_password"]


def _get_secrets():
    with g_lock:
        global g_secrets
        if g_secrets is None:
            client = google.cloud.secretmanager.SecretManagerServiceClient()
            cloud_project = os.environ["GOOGLE_CLOUD_PROJECT"]
            secret_name = f"projects/{cloud_project}/secrets/secrets/versions/latest"
            resp = client.access_secret_version(name=secret_name)
            g_secrets = json.loads(resp.payload.data)
        return g_secrets
