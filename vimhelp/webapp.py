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

_URL_PREFIX_REDIRECTS = (
    (
        (
            "http://www.vimhelp.org/",
            "https://www.vimhelp.org/",
            "http://vimhelp.appspot.com/",
            "https://vimhelp.appspot.com/",
            "http://vimhelp.org/",
        ),
        "https://vimhelp.org",
    ),
    (
        ("http://neo.vimhelp.org/",),
        "https://vimhelp.org",
    ),
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
    )

    is_dev = os.environ.get("VIMHELP_ENV") == "dev"
    if not is_dev:
        app.config["PREFERRED_URL_SCHEME"] = "https"

    @app.before_request
    def before():
        req = flask.request

        # Redirect away from legacy / non-HTTPS URL prefixes
        if req.path not in (_WARMUP_PATH, "/update"):
            for redir_from, redir_to in _URL_PREFIX_REDIRECTS:
                if req.url_root in redir_from:
                    new_url = redir_to + req.root_path + req.full_path
                    logging.info("redirecting to %s", new_url)
                    return flask.redirect(new_url, HTTPStatus.MOVED_PERMANENTLY)

        # Flask's subdomain matching doesn't seem compatible with having multiple valid
        # server names (in particular, Google Cloud calls the /update endpoint with
        # something other than vimhelp.org), so we do it this way.
        flask.g.project = (
            "neovim"
            if req.blueprint == "neovim" or req.host.startswith("neo.")
            else "vim"
        )

    @app.route(_WARMUP_PATH)
    def warmup():
        for project in ("vim", "neovim"):
            flask.g.project = project
            vimhelp.handle_vimhelp("", cache)
            tagsearch.handle_tagsearch(cache)
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
        return app.send_static_file(f"favicon-{flask.g.project}.ico")

    bp.add_url_rule("/robots.txt", view_func=robots.handle_robots_txt)
    bp.add_url_rule("/sitemap.txt", view_func=robots.handle_sitemap_txt)
    bp.add_url_rule("/update", view_func=update.UpdateHandler.as_view("update"))
    bp.add_url_rule("/enqueue_update", view_func=update.handle_enqueue_update)

    app.register_blueprint(bp, name="vim")

    if is_dev:
        app.register_blueprint(bp, name="neovim", url_prefix="/neovim")

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
