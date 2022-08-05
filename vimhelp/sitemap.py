# Generate 'sitemap.txt' on the fly.

import operator

import flask

from . import dbmodel

BASE_URL = "https://vimhelp.org/"


def handle_sitemap():
    with dbmodel.ndb_client.context():
        all_names = dbmodel.ProcessedFileHead.query().map(
            operator.methodcaller("string_id"), keys_only=True
        )
    return flask.Response(
        BASE_URL
        + "\n"
        + "".join(
            BASE_URL + name + ".html\n"
            for name in sorted(all_names)
            if name != "help.txt"
        ),
        mimetype="text/plain",
    )
