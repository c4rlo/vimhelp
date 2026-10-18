import gevent.util


accesslog = "-"
reload = True
timeout = 15
worker_class = "gevent"
wsgi_app = "vimhelp.webapp:create_app()"


def worker_abort(_worker):
    gevent.util.print_run_info()
