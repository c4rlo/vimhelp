# import gevent
import gevent.monkey

# gevent.config.track_greenlet_tree = False
gevent.monkey.patch_all()

import grpc.experimental.gevent  # noqa: E402

grpc.experimental.gevent.init_gevent()

import flask  # noqa: E402

import logging  # noqa: E402


def create_app():
    from . import sitemap
    from . import vimhelp
    from . import update

    logging.basicConfig(level=logging.INFO)

    app = flask.Flask(__name__)

    @app.route('/<filename>')
    def vimhelp_filename(filename):
        return vimhelp.handle_vimhelp(filename)

    @app.route('/')
    def vimhelp_root():
        return vimhelp.handle_vimhelp('')

    @app.route('/_ah/warmup')
    def vimhelp_warmup():
        return vimhelp.handle_vimhelp('', is_warmup=True)

    app.add_url_rule('/update',
                     view_func=update.UpdateHandler.as_view('update'))
    app.add_url_rule('/enqueue_update', view_func=update.handle_enqueue_update)
    app.add_url_rule('/sitemap.txt', view_func=sitemap.handle_sitemap)

    return app
