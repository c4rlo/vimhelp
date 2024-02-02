import base64
import datetime
import hashlib
import importlib.resources
import itertools
import logging
import mimetypes
import os
import threading

import flask
import flask.views
import google.cloud.ndb
import werkzeug.exceptions

from . import dbmodel
from . import secret


_DELETE_GRACE_PERIOD = datetime.timedelta(days=1)

_curr_assets = {}  # basename -> (hash, content)

_assets_written_lock = threading.Lock()
_assets_written = False


def init(app):
    for asset in _asset_resources().iterdir():
        _add_curr_asset(asset.name, asset.read_bytes())

    with app.app_context():
        for name in "vimhelp.css", "vimhelp.js":
            content = flask.render_template(name, mode="online").encode()
            _add_curr_asset(name, content)


def handle_static(name, hash_, immutable=True):
    if hash_ is None:
        hash_ = _curr_asset_hash(name)
    if asset := _get_asset(name, hash_):
        mimetype, _ = mimetypes.guess_type(name)
        logging.info("Serving static asset %s/%s (%s)", hash_, name, mimetype)
        resp = flask.Response(asset, mimetype=mimetype)
        if immutable:
            resp.cache_control.immutable = True
            resp.cache_control.max_age = 3600 * 24 * 365
        else:
            resp.cache_control.max_age = 3600 * 24
        return resp
    logging.warning("Static asset %s/%s not found", hash_, name)
    raise werkzeug.exceptions.NotFound()


def static_path(name):
    return f"/s/{_curr_asset_hash(name)}/{name}"


def curr_asset_ids():
    return [f"{name}:{hash_}" for name, (hash_, _) in _curr_assets.items()]


def ensure_curr_assets_in_db():
    # Caller must already be in an ndb context
    if not _do_ensure_curr_assets_in_db():
        logging.info("No new assets to write to datastore")


def clean_unused_assets():
    logging.info("Cleaning up unused assets")
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    recent = now - _DELETE_GRACE_PERIOD
    with dbmodel.ndb_context():
        all_asset_ids = {key.id() for key in dbmodel.Asset.query().iter(keys_only=True)}
        pfh_query = dbmodel.ProcessedFileHead.query(projection=["used_assets"])
        used_asset_ids = set(itertools.chain(*(pfh.used_assets for pfh in pfh_query)))
        unused_asset_ids = all_asset_ids - used_asset_ids
        unused_asset_keys = [google.cloud.ndb.Key("Asset", i) for i in unused_asset_ids]
        unused_assets = google.cloud.ndb.get_multi(unused_asset_keys)
        to_delete = []
        to_put = []
        for asset in unused_assets:
            if asset.create_time >= recent:
                continue
            if asset.unused_time is not None:
                if asset.unused_time < recent:
                    to_delete.append(asset.key)
            else:
                asset.unused_time = now
                to_put.append(asset)
        if len(to_delete) == 0 and len(to_put) == 0:
            logging.info("No assets need cleaning")
            return
        logging.info(
            "Deleting %d old asset(s) and marking %d asset(s) as unused",
            len(to_delete),
            len(to_put),
        )
        google.cloud.ndb.delete_multi(to_delete)
        google.cloud.ndb.put_multi(to_put)


def _get_asset(name, hash_):
    if a := _curr_assets.get(name):
        curr_hash, curr_content = a
        if curr_hash == hash_:
            return curr_content
    with dbmodel.ndb_context():
        if asset := dbmodel.Asset.get_by_id(f"{name}:{hash_}"):
            return asset.data
    return None


def _add_curr_asset(name, content):
    hash_ = base64.urlsafe_b64encode(hashlib.sha256(content).digest()[:12]).decode()
    _curr_assets[name] = hash_, content


def _do_ensure_curr_assets_in_db():
    with _assets_written_lock:
        global _assets_written
        if _assets_written:
            return False
        _assets_written = True

    existing_ids = {key.id() for key in dbmodel.Asset.query().iter(keys_only=True)}
    new_assets = [
        dbmodel.Asset(id=f"{name}:{hash_}", data=content)
        for name, (hash_, content) in _curr_assets.items()
        if f"{name}:{hash_}" not in existing_ids
    ]
    if len(new_assets) > 0:
        logging.info("Writing %d current asset(s) to datastore", len(new_assets))
        google.cloud.ndb.put_multi(new_assets)
        return True
    return False


def _curr_asset_hash(name):
    return _curr_assets[name][0]


def _asset_resources():
    return importlib.resources.files("vimhelp.static")


class CleanAssetsHandler(flask.views.MethodView):
    def get(self):
        if (
            os.environ.get("VIMHELP_ENV") != "dev"
            and secret.admin_password().encode() not in flask.request.query_string
        ):
            raise werkzeug.exceptions.Forbidden()
        clean_unused_assets()
        return "Success."

    def post(self):
        # https://cloud.google.com/tasks/docs/creating-appengine-handlers#reading_app_engine_task_request_headers
        if "X-AppEngine-QueueName" not in flask.request.headers:
            raise werkzeug.exceptions.Forbidden()
        clean_unused_assets()
        return flask.Response()


def handle_enqueue_clean_assets():
    req = flask.request

    is_cron = req.headers.get("X-Appengine-Cron") == "true"

    # https://cloud.google.com/appengine/docs/standard/scheduling-jobs-with-cron-yaml#securing_urls_for_cron
    if (
        not is_cron
        and os.environ.get("VIMHELP_ENV") != "dev"
        and secret.admin_password().encode() not in req.query_string
    ):
        raise werkzeug.exceptions.Forbidden()

    logging.info("Enqueueing assets clean")

    client = google.cloud.tasks.CloudTasksClient()
    queue_name = client.queue_path(
        os.environ["GOOGLE_CLOUD_PROJECT"], "us-central1", "update2"
    )
    task = {
        "app_engine_http_request": {
            "http_method": "POST",
            "relative_uri": "/clean_assets",
        }
    }
    response = client.create_task(parent=queue_name, task=task)
    logging.info("Task %s enqueued, ETA %s", response.name, response.schedule_time)

    if is_cron:
        return flask.Response()
    else:
        return "Successfully enqueued assets clean task."
