# import gevent
import gevent.monkey

# gevent.config.track_greenlet_tree = False
gevent.monkey.patch_all()

import grpc.experimental.gevent  # noqa: E402

grpc.experimental.gevent.init_gevent()

from http import HTTPStatus  # noqa: E402
import flask  # noqa: E402

import logging  # noqa: E402
import os.path  # noqa: E402


_CSP = "default-src 'self' https://cdn.jsdelivr.net"

_LEGACY_URL_PREFIXES = \
    'http://www.vimhelp.org/', 'https://www.vimhelp.org/', \
    'http://vimhelp.appspot.com/', 'https://vimhelp.appspot.com/', \
    'http://vimhelp.org/'

_WARMUP_PATH = "/_ah/warmup"


def create_app():
    from . import cache
    from . import sitemap
    from . import tagsearch
    from . import vimhelp
    from . import update

    logging.basicConfig(level=logging.INFO)

    app = flask.Flask(__name__)

    cache = cache.Cache()

    @app.before_request
    def before():
        req = flask.request
        if req.url_root in _LEGACY_URL_PREFIXES and req.path != _WARMUP_PATH:
            new_url = 'https://vimhelp.org' + req.root_path + req.full_path
            logging.info("redirecting to %s", new_url)
            return flask.redirect(new_url, HTTPStatus.MOVED_PERMANENTLY)

    @app.route('/<filename>')
    def vimhelp_filename(filename):
        return vimhelp.handle_vimhelp(filename, cache)

    @app.route('/')
    def vimhelp_root():
        return vimhelp.handle_vimhelp('', cache)

    @app.route('/help.txt.html')
    def vimhelp_help():
        return flask.redirect('/', HTTPStatus.MOVED_PERMANENTLY)

    @app.route('/api/tagsearch')
    def vimhelp_tagsearch():
        return tagsearch.handle_tagsearch(cache)

    @app.route(_WARMUP_PATH)
    def warmup():
        vimhelp.handle_vimhelp('', cache)
        tagsearch.handle_tagsearch(cache)
        return flask.Response()

    app.add_url_rule('/update',
                     view_func=update.UpdateHandler.as_view('update'))
    app.add_url_rule('/enqueue_update', view_func=update.handle_enqueue_update)
    app.add_url_rule('/sitemap.txt', view_func=sitemap.handle_sitemap)

    # These are only needed for dev. When deployed to Google App Engine,
    # these static files are served outside the scope of this app, as
    # configured in app.yaml.
    @app.route('/vimhelp.css')
    @app.route('/vimhelp.js')
    @app.route('/favicon.ico')
    @app.route('/robots.txt')
    def static_files():
        return flask.send_from_directory("../static",
                                         os.path.basename(flask.request.path))

    app.after_request(_add_default_headers)

    return app


def _add_default_headers(response: flask.Response) -> flask.Response:
    h = response.headers
    h.setdefault("Content-Security-Policy", _CSP)
    return response
