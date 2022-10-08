# Generate 'robots.txt' and 'sitemap.txt' on-the-fly.

import itertools

import flask

from . import dbmodel

BASE_URLS = {
    "vim": "https://vimhelp.org/",
    "neovim": "https://neo.vimhelp.org/",
}


def handle_robots_txt():
    project = flask.request.blueprint
    return flask.Response(
        f"Sitemap: {BASE_URLS[project]}/sitemap.txt\n", mimetype="text/plain"
    )


def handle_sitemap_txt():
    project = flask.request.blueprint
    base_url = BASE_URLS[project]

    with dbmodel.ndb_context():
        query = dbmodel.ProcessedFileHead.query(
            dbmodel.ProcessedFileHead.project == project
        )
        names = set(query.map(lambda key: key.id().split(":")[-1], keys_only=True))
        if project == "vim":
            # Add in the legacy project-less entities
            names.update(
                key.id()
                for key in dbmodel.ProcessedFileHead.query().fetch(keys_only=True)
                if ":" not in key.id()
            )
        names.discard("help.txt")

    return flask.Response(
        "".join(
            itertools.chain(
                (f"{base_url}\n",),
                (f"{base_url}{name}.html\n" for name in sorted(names)),
            )
        ),
        mimetype="text/plain",
    )
