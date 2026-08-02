# Generate 'robots.txt' and 'sitemap.txt' on-the-fly.

import itertools

import flask

from . import dbmodel

BASE_URLS = {
    "vim": "https://vimhelp.org",
    "neovim": "https://neo.vimhelp.org",
}


def handle_robots_txt():
    resp = flask.Response(
        f"Sitemap: {BASE_URLS[flask.g.project]}/sitemap.txt\n", mimetype="text/plain"
    )
    resp.cache_control.max_age = 3600 * 24
    return resp


def handle_sitemap_txt():
    project = flask.g.project
    base_url = BASE_URLS[project]

    with dbmodel.ndb_context():
        query = dbmodel.ProcessedFileHead.query(
            dbmodel.ProcessedFileHead.project == project
        )
        names = set(query.map(lambda key: key.id().split(":")[-1], keys_only=True))
        names.discard("help.txt")

    resp = flask.Response(
        "".join(
            itertools.chain(
                (f"{base_url}/\n",),
                (f"{base_url}/{name}.html\n" for name in sorted(names)),
            )
        ),
        mimetype="text/plain",
    )
    resp.cache_control.max_age = 15 * 60
    return resp
