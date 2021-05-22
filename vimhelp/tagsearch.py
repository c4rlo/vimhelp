import bisect

import flask

from . import dbmodel


MAX_RESULTS = 30
CACHE_KEY = "api/tags"


def make_result(tag, href):
    return {
        "id": tag,
        "text": tag,
        "href": href
    }


def handle_tagsearch(cache):
    query = flask.request.args.get("q", "")
    tags = cache.get(CACHE_KEY)
    if not tags:
        with dbmodel.ndb_client.context():
            tags = dbmodel.TagsInfo.get_by_id("tags").tags
            cache.put(CACHE_KEY, tags)
    len_tags = len(tags)

    # Find all tags beginning with query.
    results = []
    i = bisect.bisect_left(tags, [query, ""])
    while i < len_tags and len(results) < MAX_RESULTS \
            and tags[i][0].startswith(query):
        results.append(make_result(*tags[i]))
        i += 1

    # If we didn't find enough, additionally find all tags that contains query
    # as a substring.
    i = 0
    while i < len_tags and len(results) < MAX_RESULTS:
        item = tags[i]
        if query in item[0]:
            results.append(make_result(*item))
        i += 1

    return flask.jsonify({"results": results})
