import bisect

import flask
import werkzeug.exceptions

from . import dbmodel


# There are about 10k tags. To optimize performance, consider:
# - Dealing with 'bytes' not 'str'
# - Giving this module the Cython treatment


MAX_RESULTS = 30
CACHE_KEY_ID = "api/tag-items"


class TagItem:
    def __init__(self, tag, href):
        self.tag = tag
        self.tag_lower = tag.casefold()
        self.href = href

    def __lt__(self, query):
        # This is enough for bisect_left to work...
        return self.tag < query


def handle_tagsearch(cache):
    project = flask.g.project
    query = flask.request.args.get("q", "")
    items = cache.get(project, CACHE_KEY_ID)
    if not items:
        with dbmodel.ndb_context():
            entity = dbmodel.TagsInfo.get_by_id(project)
            if entity is None:
                raise werkzeug.exceptions.NotFound()
            items = [TagItem(*tag) for tag in entity.tags]
            cache.put(project, CACHE_KEY_ID, items)

    results = do_handle_tagsearch(items, query)
    return flask.jsonify({"results": results})


def do_handle_tagsearch(items, query):
    results = []
    result_set = set()

    is_lower = query == query.casefold()

    def add_result(item):
        if item.tag in result_set:
            return False
        results.append({"id": item.tag, "text": item.tag, "href": item.href})
        result_set.add(item.tag)
        return len(results) == MAX_RESULTS

    # Find all tags beginning with query.
    i = bisect.bisect_left(items, query)
    for item in items[i:]:
        if item.tag.startswith(query):
            if add_result(item):
                return results
        else:
            break

    # If we didn't find enough, and the query is all-lowercase, add all case-insensitive
    # matches.
    if is_lower:
        for item in items:
            if item.tag_lower.startswith(query):
                if add_result(item):
                    return results

    # If we still didn't find enough, additionally find all tags that contain query as a
    # substring.
    for item in items:
        if query in item.tag:
            if add_result(item):
                return results

    # If we still didn't find enough, and the query is all-lowercase, additionally find
    # all tags that contain query as a substring case-insensitively.
    if is_lower:
        for item in items:
            if query in item.tag_lower:
                if add_result(item):
                    return results

    return results
