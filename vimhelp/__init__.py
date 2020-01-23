def create_app():
    import logging

    import flask
    import gevent
    import gevent.monkey

    import grpc.experimental.gevent

    from . import sitemap
    from . import vimhelp
    from . import update

    logging.basicConfig(level=logging.INFO)

    gevent.config.track_greenlet_tree = False
    gevent.monkey.patch_all()
    grpc.experimental.gevent.init_gevent()

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
