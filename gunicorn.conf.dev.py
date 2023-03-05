import traceback


loglevel = "debug"
reload = True
reload_extra_files = ["static", "templates"]
timeout = 15
worker_class = "gevent"
wsgi_app = "vimhelp.webapp:create_app()"


def worker_abort(worker):
    traceback.print_stack()
