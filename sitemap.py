# Generate 'sitemap.txt' on the fly.

import dbmodel
import main

import flask

import operator

BASE_URL = 'https://vimhelp.org/'


@main.app.route('/sitemap.txt')
def sitemap():
    all_names = dbmodel.ProcessedFileHead.query() \
        .map(operator.methodcaller('string_id'), keys_only=True)
    return flask.Response(
        BASE_URL + '\n' + ''.join(
            BASE_URL + name + '.html\n'
            for name in sorted(all_names)
            if name != 'help.txt'),
        mimetype='text/plain')
