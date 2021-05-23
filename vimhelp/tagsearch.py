import bisect

import flask

from . import dbmodel


MAX_RESULTS = 30
CACHE_KEY = "api/tags"


def handle_tagsearch(cache):
    query = flask.request.args.get("q", "")
    tags = cache.get(CACHE_KEY)
    if not tags:
        with dbmodel.ndb_client.context():
            tags = dbmodel.TagsInfo.get_by_id("tags").tags
            cache.put(CACHE_KEY, tags)

    results = do_handle_tagsearch(tags, query)
    return flask.jsonify({"results": results})


def do_handle_tagsearch(tags, query):
    len_tags = len(tags)
    query_cf = query.casefold()
    results = []
    result_set = set()

    def add_result(item):
        tag, href = item
        if tag in result_set:
            return
        results.append({"id": tag, "text": tag, "href": href})
        result_set.add(tag)

    # Find all tags beginning with query.
    i = bisect.bisect_left(tags, [query, ""])
    while i < len_tags and len(results) < MAX_RESULTS \
            and tags[i][0].startswith(query):
        add_result(tags[i])
        i += 1

    # If we didn't find enough, add all case-insensitive matches.
    i = 0
    while i < len_tags and len(results) < MAX_RESULTS:
        item = tags[i]
        if item[0].casefold().startswith(query_cf):
            add_result(item)
        i += 1

    # If we still didn't find enough, additionally find all tags that contain
    # query as a substring.
    i = 0
    while i < len_tags and len(results) < MAX_RESULTS:
        item = tags[i]
        if query in item[0]:
            add_result(item)
        i += 1

    # If we still didn't find enough, additionally find all tags that contain
    # query as a substring case-insensitively.
    i = 0
    while i < len_tags and len(results) < MAX_RESULTS:
        item = tags[i]
        if query_cf in item[0].casefold():
            add_result(item)
        i += 1

    return results
