# import gevent
import gevent.monkey

# gevent.config.track_greenlet_tree = False
gevent.monkey.patch_all()

import grpc.experimental.gevent  # noqa: E402

grpc.experimental.gevent.init_gevent()

from http import HTTPStatus  # noqa: E402
import flask  # noqa: E402

import logging  # noqa: E402
import os  # noqa: E402
import pathlib  # noqa: E402


_CSP = "default-src 'self' https://cdn.jsdelivr.net"

_LEGACY_URL_PREFIXES = (
    "http://www.vimhelp.org/",
    "https://www.vimhelp.org/",
    "http://vimhelp.appspot.com/",
    "https://vimhelp.appspot.com/",
    "http://vimhelp.org/",
)

_WARMUP_PATH = "/_ah/warmup"


def create_app():
    from . import cache
    from . import robots
    from . import tagsearch
    from . import vimhelp
    from . import update

    package_path = pathlib.Path(__file__).resolve().parent

    logging.basicConfig(level=logging.INFO)

    cache = cache.Cache()

    app = flask.Flask(
        "vimhelp",
        root_path=package_path,
        static_url_path="",
        static_folder="../static",
        subdomain_matching=True,
    )
    app.config["PREFERRED_URL_SCHEME"] = "https"

    is_dev = os.environ.get("VIMHELP_ENV") == "dev"
    if not is_dev:
        app.config["SERVER_NAME"] = {
            "vimhelp-staging": "staging.vimhelp.org",
            "vimhelp-hrd": "vimhelp.org",
        }[os.environ["GOOGLE_CLOUD_PROJECT"]]

    @app.before_request
    def before():
        req = flask.request
        if req.url_root in _LEGACY_URL_PREFIXES and req.path != _WARMUP_PATH:
            new_url = "https://vimhelp.org" + req.root_path + req.full_path
            logging.info("redirecting to %s", new_url)
            return flask.redirect(new_url, HTTPStatus.MOVED_PERMANENTLY)
        if req.url_root == "http://neo.vimhelp.org/" and req.path != _WARMUP_PATH:
            new_url = "https://neo.vimhelp.org" + req.root_path + req.full_path
            logging.info("redirecting to %s", new_url)
            return flask.redirect(new_url, HTTPStatus.MOVED_PERMANENTLY)

    @app.route(_WARMUP_PATH)
    def warmup():
        for project in ("vim", "neovim"):
            vimhelp.handle_vimhelp("", cache, project_override=project)
            tagsearch.handle_tagsearch(cache, project_override=project)
        return flask.Response()

    bp = flask.Blueprint("bp", "vimhelp", root_path=package_path)

    @bp.route("/<filename>.html")
    @bp.route("/", defaults={"filename": ""})
    def vimhelp_filename(filename):
        return vimhelp.handle_vimhelp(filename, cache)

    @bp.route("/api/tagsearch")
    def vimhelp_tagsearch():
        return tagsearch.handle_tagsearch(cache)

    @bp.route("/favicon.ico")
    def favicon():
        project = flask.request.blueprint
        return app.send_static_file(f"favicon-{project}.ico")

    bp.add_url_rule("/update", view_func=update.UpdateHandler.as_view("update"))
    bp.add_url_rule("/enqueue_update", view_func=update.handle_enqueue_update)
    bp.add_url_rule("/robots.txt", view_func=robots.handle_robots_txt)
    bp.add_url_rule("/sitemap.txt", view_func=robots.handle_sitemap_txt)

    app.register_blueprint(bp, name="vim")

    if is_dev:
        app.register_blueprint(bp, name="neovim", url_prefix="/neovim")
    else:
        app.register_blueprint(bp, name="neovim", subdomain="neo")

    app.after_request(_add_default_headers)

    return app


def _add_default_headers(response: flask.Response) -> flask.Response:
    h = response.headers
    h.setdefault("Content-Security-Policy", _CSP)
    # The following is needed for local dev scenarios where one is accessing an HTML
    # file on disk ('file://' protocol) and wants it to be able to consume the tagsearch
    # API.
    # h.setdefault("Access-Control-Allow-Origin", "*")
    return response
