# ruff: noqa: E402

import gevent
import gevent.monkey

# gevent.config.track_greenlet_tree = False
gevent.monkey.patch_all()

import grpc.experimental.gevent

grpc.experimental.gevent.init_gevent()

from http import HTTPStatus
import flask
import werkzeug.exceptions

import logging
import os
from pathlib import Path


_CSP = "default-src 'self'"  # Content Security Policy

_URL_PREFIX_REDIRECTS = (
    (
        # From
        (
            "http://www.vimhelp.org/",
            "https://www.vimhelp.org/",
            "http://vimhelp.appspot.com/",
            "https://vimhelp.appspot.com/",
            "http://vimhelp.org/",
        ),
        # To
        "https://vimhelp.org",
    ),
    (
        # From
        ("http://neo.vimhelp.org/",),
        # To
        "https://neo.vimhelp.org",
    ),
)

_WARMUP_PATH = "/_ah/warmup"


def create_app() -> flask.Flask:
    from . import assets
    from . import cache
    from . import robots
    from . import tagsearch
    from . import update
    from . import vimh2h
    from . import vimhelp

    logging.basicConfig(level=logging.INFO)

    cache_ = cache.Cache()

    app = flask.Flask(
        "vimhelp", root_path=str(Path(__file__).resolve().parent), static_folder=None
    )

    app.jinja_options["trim_blocks"] = True
    app.jinja_options["lstrip_blocks"] = True
    app.jinja_env.filters["static_path"] = assets.static_path

    is_dev = os.environ.get("VIMHELP_ENV") == "dev"
    if not is_dev:
        app.config["PREFERRED_URL_SCHEME"] = "https"

    assets.init(app)

    app.add_url_rule(
        "/clean_assets", view_func=assets.CleanAssetsHandler.as_view("clean_assets")
    )
    app.add_url_rule(
        "/enqueue_clean_assets", view_func=assets.handle_enqueue_clean_assets
    )

    @app.route("/<filename>.html")
    @app.route("/", defaults={"filename": ""})
    def vimhelp_filename(filename):
        req = flask.request
        if req.method in ("GET", "HEAD") and req.query_string:
            logging.info("redirecting %s to query-free documentation URL", req.url)
            return flask.redirect(req.path, HTTPStatus.MOVED_PERMANENTLY)
        return vimhelp.handle_vimhelp(filename, cache_)

    @app.route("/s/<hash_>/<filename>")
    def static_filename(hash_, filename):
        return assets.handle_static(filename, hash_)

    @app.route("/api/tagsearch")
    def vimhelp_tagsearch():
        return tagsearch.handle_tagsearch(cache_)

    # Use a query parameter because help topics can start with '/', which Flask's
    # standard path converter rejects even when URL-encoded.
    @app.route("/go")
    def vimhelp_go():
        return tagsearch.handle_go(cache_)

    @app.route("/opensearch.xml")
    def opensearch():
        project = vimh2h.PROJECTS[flask.g.project]
        return flask.Response(
            flask.render_template(
                "opensearch.xml",
                project=project,
                search_url=flask.url_for("vimhelp_go", _external=True),
                self_url=flask.url_for("opensearch", _external=True),
                image_url=flask.url_for("favicon", _external=True),
            ),
            mimetype="application/opensearchdescription+xml",
        )

    @app.route("/favicon.ico")
    def favicon():
        return assets.handle_static(
            f"favicon-{flask.g.project}.ico", None, immutable=False
        )

    app.add_url_rule("/robots.txt", view_func=robots.handle_robots_txt)
    app.add_url_rule("/sitemap.txt", view_func=robots.handle_sitemap_txt)
    app.add_url_rule("/update", view_func=update.UpdateHandler.as_view("update"))
    app.add_url_rule("/enqueue_update", view_func=update.handle_enqueue_update)

    @app.errorhandler(werkzeug.exceptions.HTTPException)
    def http_error(error):
        message = error.description
        if (
            error.code == HTTPStatus.NOT_FOUND
            and message == werkzeug.exceptions.NotFound.description
        ):
            message = (
                "The requested page could not be found. "
                "Check the address or use the quick links above."
            )
        response = error.get_response()
        response.data = flask.render_template(
            "error.html",
            error=error,
            message=message,
            project=vimh2h.PROJECTS[flask.g.project],
            home_url=flask.url_for("vimhelp_filename"),
        )
        response.content_type = "text/html; charset=utf-8"
        return response

    def do_warmup(project):
        logging.info("doing warmup request for %s", project)
        with app.test_request_context():
            flask.g.project = project
            vimhelp.handle_vimhelp("", cache_)
            vimhelp.handle_vimhelp("options.txt", cache_)
            tagsearch.handle_tagsearch(cache_)

    @app.route(_WARMUP_PATH)
    def warmup():
        for project in ("vim", "neovim"):
            do_warmup(project)
        return flask.Response()

    @app.before_request
    def select_project():
        flask.g.project = (
            "neovim"
            if flask.request.host.startswith(("neo.", "staging-neo."))
            else "vim"
        )

    @app.before_request
    def redirect_canonical_url():
        req = flask.request

        # Redirect away from legacy / non-HTTPS URL prefixes
        if req.path not in (_WARMUP_PATH, "/update"):
            for redir_from, redir_to in _URL_PREFIX_REDIRECTS:
                if req.url_root in redir_from:
                    path = req.full_path if req.query_string else req.path
                    new_url = redir_to + req.root_path + path
                    logging.info("redirecting %s to %s", req.url, new_url)
                    return flask.redirect(new_url, HTTPStatus.MOVED_PERMANENTLY)

    @app.after_request
    def add_default_headers(response: flask.Response) -> flask.Response:
        h = response.headers
        h.setdefault("Content-Security-Policy", _CSP)
        # Allow HTML files opened via file:// to consume the local tagsearch API.
        if is_dev:
            h.setdefault("Access-Control-Allow-Origin", "*")
        return response

    gevent.spawn(cache_.start_refresh_loop, do_warmup)

    logging.info("app initialised")

    return app
