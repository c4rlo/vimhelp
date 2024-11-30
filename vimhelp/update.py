# Regularly scheduled update: check which files need updating and translate them

import base64
import datetime
import hashlib
import itertools
import json
import logging
import os
import re
from http import HTTPStatus

import flask
import flask.views
import gevent
import gevent.pool
import werkzeug.exceptions

import google.cloud.ndb
import google.cloud.tasks

from .dbmodel import (
    GlobalInfo,
    ProcessedFileHead,
    ProcessedFilePart,
    RawFileContent,
    RawFileInfo,
    TagsInfo,
    ndb_context,
)
from .http import HttpClient, HttpResponse
from . import assets
from . import secret
from . import vimh2h


# Once we have consumed about ten minutes of CPU time, Google will throw us a
# DeadlineExceededError and our script terminates. Therefore, we must be careful with
# the order of operations, to ensure that after this has happened, the next scheduled
# run of the script can pick up where the previous one was interrupted. Although in
# practice, it takes about 30 seconds, so it's unlikely to be an issue.

# Number of concurrent (in the gevent sense) workers. Avoid setting this too high, else
# there is risk of running out of memory on our puny worker node.
CONCURRENCY = 5

# Max size in bytes of processed file part to store in a single entity in the datastore.
# Note that datastore entities have a maximum size of just under 1 MiB.
MAX_DB_PART_LEN = 995000

TAGS_NAME = "tags"
HELP_NAME = "help.txt"
FAQ_NAME = "vim_faq.txt"
MATCHIT_NAME = "matchit.txt"
EDITORCONFIG_NAME = "editorconfig.txt"
EXTRA_NAMES = TAGS_NAME, MATCHIT_NAME, EDITORCONFIG_NAME

DOC_ITEM_RE = re.compile(r"(?:[-\w]+\.txt|tags)$")
VERSION_TAG_RE = re.compile(r"v?(\d[\w.+-]+)$")

GITHUB_DOWNLOAD_URL_BASE = "https://raw.githubusercontent.com/"
GITHUB_GRAPHQL_API_URL = "https://api.github.com/graphql"

FAQ_BASE_URL = "https://raw.githubusercontent.com/chrisbra/vim_faq/master/doc/"

GITHUB_GRAPHQL_QUERIES = {
    "GetRefs": """
        query GetRefs($org: String!, $repo: String!) {
          repository(owner: $org, name: $repo) {
            defaultBranchRef {
              target {
                oid
              }
            }
            refs(refPrefix: "refs/tags/",
                 orderBy: {field: TAG_COMMIT_DATE, direction: DESC},
                 first: 5) {
              nodes {
                name
              }
            }
          }
        }
        """,
    "GetDirs": """
        query GetDirs($org: String!, $repo: String!,
                      $expr1: String!, $expr2: String!, $expr3: String!) {
          repository(owner: $org, name: $repo) {
            dir1: object(expression: $expr1) {
              ...treeEntries
            }
            dir2: object(expression: $expr2) {
              ...treeEntries
            }
            dir3: object(expression: $expr3) {
              ...treeEntries
            }
          }
        }
        fragment treeEntries on GitObject {
          ...on Tree {
            entries {
              type
              name
              oid
            }
          }
        }
        """,
}


class UpdateHandler(flask.views.MethodView):
    def post(self):
        # We get an HTTP POST request if the request came programmatically via Cloud
        # Tasks.
        self._run(flask.request.data)
        return flask.Response()

    def get(self):
        # We get an HTTP GET request if the request was generated by the user, by
        # entering the URL in their browser.
        self._run(flask.request.query_string)
        return "Success."

    def _run(self, request_data):
        req = flask.request

        # https://cloud.google.com/tasks/docs/creating-appengine-handlers#reading_app_engine_task_request_headers
        if (
            "X-AppEngine-QueueName" not in req.headers
            and os.environ.get("VIMHELP_ENV") != "dev"
            and secret.admin_password().encode() not in request_data
        ):
            raise werkzeug.exceptions.Forbidden()

        is_force = b"force" in request_data

        if b"project=vim" in request_data:
            self._project = "vim"
        elif b"project=neovim" in request_data:
            self._project = "neovim"
        else:
            self._project = flask.g.project

        logging.info(
            "Starting %supdate for %s", "forced " if is_force else "", self._project
        )

        self._app = flask.current_app._get_current_object()
        self._http_client = HttpClient(CONCURRENCY)

        try:
            self._greenlet_pool = gevent.pool.Pool(size=CONCURRENCY)

            with ndb_context():
                self._g = self._init_g(wipe=is_force)
                self._g_dict_pre = self._g.to_dict()
                self._had_exception = False
                if self._project == "vim":
                    self._do_update_vim(no_rfi=is_force)
                elif self._project == "neovim":
                    self._do_update_neovim(no_rfi=is_force)
                else:
                    raise RuntimeError(f"unknown project '{self._project}'")

                if not self._had_exception and self._g_dict_pre != self._g.to_dict():
                    self._g.put()
                    logging.info(
                        "Finished %s update, updated global info", self._project
                    )
                else:
                    logging.info(
                        "Finished %s update, global info not updated", self._project
                    )

            self._greenlet_pool.join()
        finally:
            self._http_client.close()

    def _init_g(self, wipe):
        """Initialize 'self._g' (GlobalInfo)"""
        g = GlobalInfo.get_by_id(self._project)

        if wipe:
            logging.info(
                "Deleting %s global info and raw files from Datastore", self._project
            )
            greenlets = [
                self._spawn(wipe_db, RawFileContent, self._project),
                self._spawn(wipe_db, RawFileInfo, self._project),
            ]
            if g:
                greenlets.append(self._spawn(g.key.delete))
                g = None
            gevent.joinall(greenlets)

        if not g:
            g = GlobalInfo(id=self._project, last_update_time=utcnow())

        gs = ", ".join(f"{n} = {getattr(g, n)}" for n in g._properties.keys())  # noqa: SIM118
        logging.info("%s global info: %s", self._project, gs)

        return g

    def _do_update_vim(self, no_rfi):
        old_vim_version_tag = self._g.vim_version_tag
        old_master_sha = self._g.master_sha

        # Kick off retrieval of master branch SHA and vim version from GitHub
        get_git_refs_greenlet = self._spawn(self._get_git_refs)

        # Kick off retrieval of all RawFileInfo entities from the Datastore
        rfi_greenlet = self._spawn(self._get_all_rfi, no_rfi)

        # Check whether the master branch is updated, and whether we have a new vim
        # version
        get_git_refs_greenlet.get()
        is_master_updated = self._g.master_sha != old_master_sha
        is_new_vim_version = self._g.vim_version_tag != old_vim_version_tag

        if is_master_updated:
            # Kick off retrieval of doc dirs listing in GitHub. This is against
            # the 'master' branch, since the docs often get updated after the tagged
            # commits that introduce the relevant changes.
            docdir_greenlet = self._spawn(self._list_docs_dir, self._g.master_sha)
        else:
            # No need to list doc dir if nothing changed
            docdir_greenlet = None

        # Put all RawFileInfo entities into a map
        self._rfi_map = rfi_greenlet.get()

        # Kick off FAQ download (this also writes the raw file to the datastore, if
        # modified)
        faq_greenlet = self._spawn(self._get_file, FAQ_NAME, "http")

        # Iterate over doc dirs listing (which also updates the items in
        # 'self._rfi_map') and collect list of new/modified files
        if docdir_greenlet is None:
            logging.info("No need to get new doc dir listing")
            updated_file_names = set()
        else:
            updated_file_names = {
                name for name, is_modified in docdir_greenlet.get() if is_modified
            }

        # Check FAQ download result
        faq_result = faq_greenlet.get()
        if not faq_result.is_modified:
            if len(updated_file_names) == 0 and not is_new_vim_version:
                logging.info("Nothing to do")
                return
            faq_result = None
            faq_greenlet = self._spawn(self._get_file, FAQ_NAME, "db")

        # Write current versions of static assets (vimhelp.js etc) to datastore
        assets_greenlet = self._spawn(assets.ensure_curr_assets_in_db)

        # Get extra files from GitHub or datastore, depending on whether they were
        # changed
        extra_greenlets = {}
        for name in EXTRA_NAMES:
            if name in updated_file_names:
                updated_file_names.remove(name)
                sources = "http,db"
            else:
                sources = "db"
            extra_greenlets[name] = self._spawn(self._get_file, name, sources)

        extra_results = {name: extra_greenlets[name].get() for name in EXTRA_NAMES}
        extra_results[FAQ_NAME] = faq_result or faq_greenlet.get()
        tags_result = extra_results[TAGS_NAME]

        logging.info("Beginning vimhelp-to-HTML translations")

        self._g.last_update_time = utcnow()

        # Construct the vimhelp-to-html translator, providing it the tags file content,
        # and adding on the extra files from which to source more tags
        self._h2h = vimh2h.VimH2H(
            mode="online",
            project="vim",
            version=version_from_tag(self._g.vim_version_tag),
            tags=tags_result.content.decode(),
        )
        for name, result in extra_results.items():
            if name != TAGS_NAME:
                self._h2h.add_tags(name, result.content.decode())

        # Ensure all assets are in the datastore by now
        assets_greenlet.get()

        greenlets = []

        def track_spawn(f, *args, **kwargs):
            greenlets.append(self._spawn(f, *args, **kwargs))

        # Save tags JSON if we may have updated tags
        if any(result.is_modified for result in extra_results.values()):
            track_spawn(self._save_tags_json)

        # Translate each extra file if either it, or the tags file, was modified
        # (a changed tags file can lead to different outgoing links)
        for name, result in extra_results.items():
            if result.is_modified or tags_result.is_modified:
                track_spawn(self._translate, name, result.content)

        # If we found a new vim version, ensure we translate help.txt, since we're
        # displaying the current vim version in the rendered help.txt.html
        if is_new_vim_version:
            track_spawn(
                self._get_file_and_translate, HELP_NAME, translate_if_not_modified=True
            )
            updated_file_names.discard(HELP_NAME)

        # Translate all other modified files, after retrieving them from GitHub or
        # datastore (this also writes the raw file info to the datastore, if modified)
        # TODO: theoretically we should re-translate all files (whether in
        # updated_file_names or not) if the tags file was modified
        for name in updated_file_names:
            track_spawn(
                self._get_file_and_translate, name, translate_if_not_modified=False
            )

        logging.info("Waiting for everything to finish")

        self._join_greenlets(greenlets)

    def _do_update_neovim(self, no_rfi):
        # Check whether we have a new Neovim version
        old_vim_version_tag = self._g.vim_version_tag
        self._get_git_refs()
        if self._g.vim_version_tag == old_vim_version_tag:
            logging.info("Nothing to do")
            return

        # Write current versions of static assets (vimhelp.js etc) to datastore
        assets_greenlet = self._spawn(assets.ensure_curr_assets_in_db)

        # Kick off retrieval of all RawFileInfo entities from the Datastore
        rfi_greenlet = self._spawn(self._get_all_rfi, no_rfi)

        # Kick off retrieval of doc dirs listing in GitHub for the current
        # version.
        docdir_greenlet = self._spawn(self._list_docs_dir, self._g.vim_version_tag)

        # Put all RawFileInfo entities into a map
        self._rfi_map = rfi_greenlet.get()

        self._g.last_update_time = utcnow()

        self._h2h = vimh2h.VimH2H(
            mode="online",
            project="neovim",
            version=version_from_tag(self._g.vim_version_tag),
        )

        # Iterate over doc dirs listing (which also updates the items in
        # 'self._rfi_map'), kicking off retrieval of files and addition of help tags to
        # 'self._h2h'; file retrieval also includes writing the raw file to the
        # datastore if modified
        all_file_names = set()
        for name, is_modified in docdir_greenlet.get():
            all_file_names.add(name)
            sources = "http,db" if is_modified else "db"
            self._spawn(self._get_file_and_add_tags, name, sources)

        # Wait for all tag additions to complete
        self._greenlet_pool.join(raise_error=True)

        # Save tags JSON
        greenlets = [self._spawn(self._save_tags_json)]

        # Ensure all assets are in the datastore by now
        assets_greenlet.get()

        logging.info("Beginning vimhelp-to-HTML conversions")

        # Kick off processing of all files, reading file contents from the Datastore,
        # where we just saved them all
        for name in all_file_names:
            greenlets.append(
                self._spawn(
                    self._get_file_and_translate,
                    name,
                    translate_if_not_modified=True,
                    sources="db",
                )
            )

        self._join_greenlets(greenlets)

    def _get_git_refs(self):
        """
        Populate 'master_sha', 'vim_version_tag, 'refs_etag' members of 'self._g'
        (GlobalInfo)
        """
        # Hmm, the GitHub GraphQL API does not seem to actually support ETag:
        # https://github.com/github-community/community/discussions/10799
        r = self._github_graphql_request(
            "GetRefs",
            variables={"org": self._project, "repo": self._project},
            etag=self._g.refs_etag,
        )
        if r.status_code == HTTPStatus.OK:
            etag_str = r.header("ETag")
            etag = etag_str.encode() if etag_str is not None else None
            if etag == self._g.refs_etag:
                logging.info(
                    "%s GetRefs query ETag unchanged (%s)", self._project, etag
                )
            else:
                logging.info(
                    "%s GetRefs query ETag changed: %s -> %s",
                    self._project,
                    self._g.refs_etag,
                    etag,
                )
                self._g.refs_etag = etag
            resp = json.loads(r.body)["data"]["repository"]
            latest_sha = resp["defaultBranchRef"]["target"]["oid"]
            if latest_sha == self._g.master_sha:
                logging.info("%s master SHA unchanged (%s)", self._project, latest_sha)
            else:
                logging.info(
                    "%s master SHA changed: %s -> %s",
                    self._project,
                    self._g.master_sha,
                    latest_sha,
                )
                self._g.master_sha = latest_sha
            tags = resp["refs"]["nodes"]
            latest_version_tag = None
            for tag in tags:
                tag_name = tag["name"]
                if VERSION_TAG_RE.match(tag_name):
                    latest_version_tag = tag_name
                    break
            if latest_version_tag == self._g.vim_version_tag:
                logging.info(
                    "%s version tag unchanged (%s)", self._project, latest_version_tag
                )
            else:
                logging.info(
                    "%s version tag changed: %s -> %s",
                    self._project,
                    self._g.vim_version_tag,
                    latest_version_tag,
                )
                self._g.vim_version_tag = latest_version_tag
        elif r.status_code == HTTPStatus.NOT_MODIFIED and self._g.refs_etag:
            logging.info("Initial %s GraphQL request: HTTP Not Modified", self._project)
        else:
            raise RuntimeError(
                f"Initial {self._project} GraphQL request: "
                f"bad HTTP status {r.status_code}"
            )

    def _list_docs_dir(self, git_ref):
        """
        Generator that yields '(name: str, is_modified: bool)' pairs on iteration,
        representing the set of filenames in the 'runtime/doc' and
        'runtime/pack/dist/opt/{matchit,editorconfig}/doc' directories (if they exist)
        of the current project, and whether each one is new/modified or not.
        'git_ref' is the Git ref to use when looking up the directory.
        This function both reads and writes 'self._rfi_map'.
        """
        response = self._github_graphql_request(
            "GetDirs",
            variables={
                "org": self._project,
                "repo": self._project,
                "expr1": git_ref + ":runtime/doc",
                "expr2": git_ref + ":runtime/pack/dist/opt/matchit/doc",
                "expr3": git_ref + ":runtime/pack/dist/opt/editorconfig/doc",
            },
            etag=self._g.docdir_etag,
        )
        if response.status_code == HTTPStatus.NOT_MODIFIED:
            logging.info("%s doc dir not modified", self._project)
            return
        if response.status_code != HTTPStatus.OK:
            raise RuntimeError(f"Bad doc dir HTTP status {response.status_code}")
        etag = response.header("ETag")
        self._g.docdir_etag = etag.encode() if etag is not None else None
        logging.info("%s doc dir modified, new etag is %s", self._project, etag)
        resp = json.loads(response.body)["data"]["repository"]
        done = set()  # "tags" filename exists in multiple dirs, only want first one
        entries = [(resp[d] or {}).get("entries", []) for d in ("dir1", "dir2", "dir3")]
        for item in itertools.chain(*entries):
            name = item["name"]
            if item["type"] != "blob" or not DOC_ITEM_RE.match(name) or name in done:
                continue
            done.add(name)
            git_sha = item["oid"].encode()
            rfi = self._rfi_map.get(name)
            if rfi is None:
                logging.info("Found new '%s:%s'", self._project, name)
                self._rfi_map[name] = RawFileInfo(
                    id=f"{self._project}:{name}", project=self._project, git_sha=git_sha
                )
                yield name, True
            elif rfi.git_sha == git_sha:
                logging.debug("Found unchanged '%s:%s'", self._project, name)
                yield name, False
            else:
                logging.info("Found changed '%s:%s'", self._project, name)
                rfi.git_sha = git_sha
                yield name, True

    def _github_graphql_request(self, query_name, variables=None, etag=None):
        """
        Make GitHub GraphQL API request.
        """
        logging.info("Making %s GitHub GraphQL query: %s", self._project, query_name)
        headers = {
            "Authorization": "token " + secret.github_token(),
        }
        if etag is not None:
            headers["If-None-Match"] = etag.decode()
        body = {"query": GITHUB_GRAPHQL_QUERIES[query_name]}
        if variables is not None:
            body["variables"] = variables
        response = self._http_client.post(
            GITHUB_GRAPHQL_API_URL, json=body, headers=headers
        )
        logging.info(
            "%s GitHub %s HTTP status: %s",
            self._project,
            query_name,
            response.status_code,
        )
        return response

    def _save_tags_json(self):
        """
        Obtain list of tag/link pairs from 'self._h2h' and save to Datastore.
        """
        tags = self._h2h.sorted_tag_href_pairs()
        logging.info("Saving %d %s (tag, href) pairs", len(tags), self._project)
        TagsInfo(id=self._project, tags=tags).put()

    def _get_file_and_translate(self, name, translate_if_not_modified, sources=None):
        """
        Get file with given 'name' and translate to HTML.
        'translate_if_not_modified' controls whether to translate to HTML even if the
        file was not modified.
        'sources' is as for '_get_file'; a sensible default based on
        'translate_if_not_modified' is chosen if not provided.
        """
        if sources is None:
            sources = "http,db" if translate_if_not_modified else "http"
        result = self._get_file(name, sources)
        if translate_if_not_modified or result.is_modified:
            self._translate(name, result.content)

    def _get_file_and_add_tags(self, name, sources):
        """
        Get file with given 'name' and add tags from it to 'self._h2h'.
        'sources' is as for '_get_file'.
        """
        result = self._get_file(name, sources)
        self._h2h.add_tags(name, result.content.decode())

    def _get_file(self, name, sources):
        """
        Get file with given 'name' via HTTP and/or from the Datastore, based on
        'sources', which should be one of "http", "db", "http,db". If a new/modified
        file was retrieved via HTTP, save raw file (info) to Datastore as needed.
        """
        rfi = self._rfi_map.get(name)
        result = None
        sources_set = set(sources.split(","))

        if "http" in sources_set:
            url = self._download_url(name)
            headers = {}
            if rfi is None:
                rfi = self._rfi_map[name] = RawFileInfo(
                    id=f"{self._project}:{name}", project=self._project
                )
            if rfi.etag is not None:
                headers["If-None-Match"] = rfi.etag.decode()
            logging.info("Fetching %s", url)
            response = self._http_client.get(url, headers)
            logging.info("Fetched %s -> HTTP %s", url, response.status_code)
            result = GetFileResult(response)  # raises exception on bad HTTP status
            if (etag := response.header("ETag")) is not None:
                rfi.etag = etag.encode()
            if result.is_modified:
                save_raw_file(rfi, result.content)
                return result

        if "db" in sources_set:
            logging.info("Fetching '%s:%s' from datastore", self._project, name)
            rfc = RawFileContent.get_by_id(f"{self._project}:{name}")
            logging.info("Fetched '%s:%s' from datastore", self._project, name)
            return GetFileResult(rfc)

        return result

    def _download_url(self, name):
        if name == FAQ_NAME:
            return FAQ_BASE_URL + FAQ_NAME
        ref = self._g.master_sha if self._project == "vim" else self._g.vim_version_tag
        base = f"{GITHUB_DOWNLOAD_URL_BASE}{self._project}/{self._project}/{ref}"
        if name == MATCHIT_NAME:
            return f"{base}/runtime/pack/dist/opt/matchit/doc/{name}"
        elif name == EDITORCONFIG_NAME and self._project == "vim":
            # neovim has this file in its main doc dir
            return f"{base}/runtime/pack/dist/opt/editorconfig/doc/{name}"
        else:
            return f"{base}/runtime/doc/{name}"

    def _translate(self, name, content):
        """
        Translate given file to HTML and save to Datastore.
        """
        logging.info("Translating '%s:%s' to HTML", self._project, name)
        phead, pparts = to_html(self._project, name, content, self._h2h)
        logging.info(
            "Saving HTML translation of '%s:%s' to Datastore", self._project, name
        )
        save_transactional([phead, *pparts])

    def _get_all_rfi(self, no_rfi):
        if no_rfi:
            return {}
        else:
            rfi_list = RawFileInfo.query(RawFileInfo.project == self._project).fetch()
            return {r.key.id().split(":")[1]: r for r in rfi_list}

    def _spawn(self, f, *args, **kwargs):
        def g():
            with self._app.app_context(), ndb_context():
                return f(*args, **kwargs)

        return self._greenlet_pool.spawn(g)

    def _join_greenlets(self, greenlets):
        for greenlet in gevent.iwait(greenlets):
            try:
                greenlet.get()
            except Exception as e:
                logging.error(e)
                self._had_exception = True


class GetFileResult:
    def __init__(self, obj):
        if isinstance(obj, HttpResponse):
            self.content = obj.body
            if obj.status_code == HTTPStatus.OK:
                self.is_modified = True
            elif obj.status_code == HTTPStatus.NOT_MODIFIED:
                self.is_modified = False
            else:
                raise RuntimeError(
                    f"Fetching {obj.url} yielded bad HTTP status {obj.status_code}"
                )
        elif isinstance(obj, RawFileContent):
            self.content = obj.data
            self.is_modified = False


def to_html(project, name, content, h2h):
    content_str = content.decode()
    html = h2h.to_html(name, content_str).encode()
    etag = base64.b64encode(sha1(html))
    datalen = len(html)
    phead = ProcessedFileHead(
        id=f"{project}:{name}",
        project=project,
        encoding=b"UTF-8",
        etag=etag,
        used_assets=assets.curr_asset_ids(),
    )
    pparts = []
    if datalen > MAX_DB_PART_LEN:
        phead.numparts = 0
        for i in range(0, datalen, MAX_DB_PART_LEN):
            part = html[i : (i + MAX_DB_PART_LEN)]
            if i == 0:
                phead.data0 = part
            else:
                partname = f"{project}:{name}:{phead.numparts}"
                pparts.append(ProcessedFilePart(id=partname, data=part, etag=etag))
            phead.numparts += 1
    else:
        phead.numparts = 1
        phead.data0 = html
    return phead, pparts


def save_raw_file(rfi, content):
    rfi_id = rfi.key.id()
    project, name = rfi_id.split(":")
    if project == "neovim" or name in (HELP_NAME, FAQ_NAME, *EXTRA_NAMES):
        logging.info("Saving raw file '%s' (info and content) to Datastore", rfi_id)
        rfc = RawFileContent(
            id=rfi_id, project=project, data=content, encoding=b"UTF-8"
        )
        save_transactional([rfi, rfc])
    else:
        logging.info("Saving raw file '%s' (info only) to Datastore", rfi_id)
        rfi.put()


def wipe_db(model, project):
    keys = model.query(model.project == project).fetch(keys_only=True)
    google.cloud.ndb.delete_multi(keys)


@google.cloud.ndb.transactional(xg=True)
def save_transactional(entities):
    google.cloud.ndb.put_multi(entities)


def version_from_tag(version_tag):
    if m := VERSION_TAG_RE.match(version_tag):
        return m.group(1)
    else:
        return version_tag


def sha1(content):
    digest = hashlib.sha1()  # noqa: S324
    digest.update(content)
    return digest.digest()


def utcnow():
    # datetime.datetime.utcnow() is deprecated; the following does the same thing
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def handle_enqueue_update():
    req = flask.request

    is_cron = req.headers.get("X-Appengine-Cron") == "true"

    # https://cloud.google.com/appengine/docs/standard/scheduling-jobs-with-cron-yaml#securing_urls_for_cron
    if (
        not is_cron
        and os.environ.get("VIMHELP_ENV") != "dev"
        and secret.admin_password().encode() not in req.query_string
    ):
        raise werkzeug.exceptions.Forbidden()

    logging.info("Enqueueing update")

    client = google.cloud.tasks.CloudTasksClient()
    queue_name = client.queue_path(
        os.environ["GOOGLE_CLOUD_PROJECT"], "us-central1", "update2"
    )
    body = req.query_string
    if b"project=" not in body:
        body += b"&project=" + flask.g.project.encode()
    task = {
        "app_engine_http_request": {
            "http_method": "POST",
            "relative_uri": "/update",
            "body": body,
        }
    }
    response = client.create_task(parent=queue_name, task=task)
    logging.info("Task %s enqueued, ETA %s", response.name, response.schedule_time)

    if is_cron:
        return flask.Response()
    else:
        return "Successfully enqueued update task."
