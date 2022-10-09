# Translates Vim documentation to HTML

import functools
import html
import re
import urllib.parse
from itertools import chain

HEAD_FMT = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{project.name} help pages, always up-to-date">
<title>{project.name}: {filename}</title>
<link rel="shortcut icon" href="favicon.ico">
<!-- {project.favicon_notice} -->
<link rel="stylesheet" href="/vimhelp.css" type="text/css">
"""

SEARCH_HEADERS = """
<link rel="stylesheet" class="select2-css" href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" integrity="sha256-zaSoHBhwFdle0scfGEFUCwggPN7F+ip9XRglo8IWb4w=" crossorigin="anonymous" disabled>
<script defer src="https://cdn.jsdelivr.net/npm/jquery@3.5.1/dist/jquery.min.js" integrity="sha256-9/aliU8dGd2tb6OSsuzixeV4y/faTqgFtohetphbbj0=" crossorigin="anonymous"></script>
<script defer src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js" integrity="sha256-9yRP/2EFlblE92vzCA10469Ctd0jT48HnmmMw5rJZrA=" crossorigin="anonymous"></script>
<script defer src="/vimhelp.js"></script>
"""

HEAD_END = "</head><body>"

INTRO_FMT = """
<h1>{project.name} help files</h1>
<p>This is an HTML version of the <a href="{project.url}" target="_blank" rel="noopener noreferrer">{project.name}</a> help pages, current as of {project.name} {version}.
They are kept up-to-date <a href="https://github.com/c4rlo/vimhelp" target="_blank" rel="noopener noreferrer" class="d">automatically</a>
from the <a href="{project.doc_src_url}" target="_blank" rel="noopener noreferrer" class="d">{project.name} source repository</a>.{project.faq_note}</p>

<p><a href="https://{project.other.vimdoc_site}/">Help pages</a> are also available for
<a href="{project.other.url}" target="_blank" rel="noopener noreferrer">{project.other.contrasted_name}</a>.</p>
"""

VIM_FAQ_NOTE = """
Also included is the <a href="vim_faq.txt.html">Vim FAQ</a>, kept up to date from its
<a href="https://github.com/chrisbra/vim_faq" target="_blank" rel="noopener noreferrer" class="d">GitHub repository</a>.
"""

SITENAVI_LINKS_NEOVIM_FMT = """
Quick links:
<a href="./">help overview</a> &middot;
<a href="quickref.txt.html">quick reference</a> &middot;
<a href="usr_toc.txt.html">user manual toc</a> &middot;
<a href="{helptxt}#reference_toc">reference manual toc</a>
"""

SITENAVI_LINKS_VIM_FMT = (
    SITENAVI_LINKS_NEOVIM_FMT + '&middot; <a href="vim_faq.txt.html">faq</a>'
)

SITENAVI_SEARCH_FMT = """
<div class="bar">
  <div class="ql">{sitenavi_links}</div>
  <div class="srch">
    <select id="vh-select-tag"></select>
  </div>
  <form class="srch" action="https://duckduckgo.com" method="get" target="_blank" rel="noopener noreferrer">
    <input type="hidden" name="sites" value="{project.vimdoc_site}">
    <input type="search" name="q" id="site-search-input" placeholder="Site search">
  </form>
</div>
"""

TEXTSTART = "<pre>"

FOOTER = "</pre>"

FOOTER2 = """
<footer>This site is maintained by Carlo Teubner (<i>(my first name) at cteubner dot net</i>).</footer>
</body>
</html>
"""

FAQ_LINE = '<a href="vim_faq.txt.html#vim_faq.txt" class="l">vim_faq.txt</a>   Frequently Asked Questions\n'


class VimProject:
    name = "Vim"
    contrasted_name = "the original Vim"
    url = "https://www.vim.org/"
    vimdoc_site = "vimhelp.org"
    doc_src_url = "https://github.com/vim/vim/tree/master/runtime/doc"
    favicon_notice = "favicon is based on http://amnoid.de/tmp/vim_solidbright_512.png and is used with permission by its author"
    faq_note = VIM_FAQ_NOTE
    sitenavi_links_fmt = SITENAVI_LINKS_VIM_FMT


class NeovimProject:
    name = "Neovim"
    contrasted_name = "Neovim"
    url = "https://neovim.io/"
    vimdoc_site = "neo.vimhelp.org"
    doc_src_url = "https://github.com/neovim/neovim/tree/master/runtime/doc"
    favicon_notice = "favicon taken from https://neovim.io/favicon.ico, which is licensed under CC-BY-3.0: https://creativecommons.org/licenses/by/3.0/"
    faq_note = ""
    sitenavi_links_fmt = SITENAVI_LINKS_NEOVIM_FMT


VimProject.other = NeovimProject
NeovimProject.other = VimProject


PROJECTS = {"vim": VimProject, "neovim": NeovimProject}

RE_TAGLINE = re.compile(r"(\S+)\s+(\S+)")

PAT_WORDCHAR = "[!#-)+-{}~\xC0-\xFF]"

PAT_HEADER = r"(^.*~$)"
PAT_GRAPHIC = r"(^.* `$)"
PAT_PIPEWORD = r"(?<!\\)\|([#-)!+-{}~]+)\|"
PAT_STARWORD = r"\*([#-)!+-~]+)\*(?:(?=\s)|$)"
PAT_COMMAND = r"`([^` ]+)`"
PAT_OPTWORD = r"('(?:[a-z]{2,}|t_..)')"
PAT_CTRL = r"((?:CTRL|META|ALT)-(?:W_)?(?:\{char\}|<[A-Za-z]+?>|.)?)"
PAT_SPECIAL = (
    r"(<.+?>|\{.+?}|"
    r"\[(?:range|line|count|offset|\+?cmd|[-+]?num|\+\+opt|"
    r"arg|arguments|ident|addr|group)]|"
    r"(?<=\s)\[[-a-z^A-Z0-9_]{2,}])"
)
PAT_TITLE = r"(Vim version [0-9.a-z]+|N?VIM REFERENCE.*)"
PAT_NOTE = (
    r"((?<!" + PAT_WORDCHAR + r")(?:note|NOTE|Notes?):?(?!" + PAT_WORDCHAR + r"))"
)
PAT_URL = r'((?:https?|ftp)://[^\'"<> \t]+[a-zA-Z0-9/])'
PAT_WORD = (
    r"((?<!" + PAT_WORDCHAR + r")" + PAT_WORDCHAR + r"+(?!" + PAT_WORDCHAR + r"))"
)

RE_LINKWORD = re.compile(PAT_OPTWORD + "|" + PAT_CTRL + "|" + PAT_SPECIAL)
# fmt: off
RE_TAGWORD = re.compile(
    PAT_HEADER + "|" +
    PAT_GRAPHIC + "|" +
    PAT_PIPEWORD + "|" +
    PAT_STARWORD + "|" +
    PAT_COMMAND + "|" +
    PAT_OPTWORD + "|" +
    PAT_CTRL + "|" +
    PAT_SPECIAL + "|" +
    PAT_TITLE + "|" +
    PAT_NOTE + "|" +
    PAT_URL + "|" +
    PAT_WORD
)
# fmt: on
RE_NEWLINE = re.compile(r"[\r\n]")
RE_HRULE = re.compile(r"[-=]{3,}.*[-=]{3,3}$")
RE_EG_START = re.compile(r"(?:.* )?>$")
RE_EG_END = re.compile(r"[^ \t]")
RE_SECTION = re.compile(r"[-A-Z .][-A-Z0-9 .()]*(?=\s+\*)")
RE_STARTAG = re.compile(r'\*([^ \t"*]+)\*(?:\s|$)')
RE_LOCAL_ADD = re.compile(r"LOCAL ADDITIONS:\s+\*local-additions\*$")


class Link:
    def __init__(self, filename, htmlfilename, tag):
        self.filename = filename
        self._htmlfilename = htmlfilename
        if tag == "help-tags" and filename == "tags":
            self._tag_quoted = None
        else:
            self._tag_quoted = urllib.parse.quote_plus(tag)
        self._tag_escaped = html_escape(tag)
        self._cssclass = "d"
        if m := RE_LINKWORD.match(tag):
            opt, ctrl, special = m.groups()
            if opt is not None:
                self._cssclass = "o"
            elif ctrl is not None:
                self._cssclass = "k"
            elif special is not None:
                self._cssclass = "s"

    @functools.cache
    def href(self, is_same_doc):
        if self._tag_quoted is None:
            return self._htmlfilename
        doc = "" if is_same_doc else self._htmlfilename
        return f"{doc}#{self._tag_quoted}"

    @functools.cache
    def html(self, is_pipe, is_same_doc):
        cssclass = "l" if is_pipe else self._cssclass
        return (
            f'<a href="{self.href(is_same_doc)}" class="{cssclass}">'
            f"{self._tag_escaped}</a>"
        )


class VimH2H:
    def __init__(self, project="vim", tags=None, version=None, is_web_version=True):
        self._urls = {}
        self._project = PROJECTS[project]
        self._version = version
        self._is_web_version = is_web_version
        if tags is not None:
            for line in RE_NEWLINE.split(tags):
                if m := RE_TAGLINE.match(line):
                    tag, filename = m.group(1, 2)
                    self.do_add_tag(filename, tag)
        self._urls["help-tags"] = Link("tags", "tags.html", "help-tags")

    def add_tags(self, filename, contents):
        in_example = False
        for line in RE_NEWLINE.split(contents):
            if in_example:
                if RE_EG_END.match(line):
                    in_example = False
                else:
                    continue
            for anchor in RE_STARTAG.finditer(line):
                tag = anchor.group(1)
                self.do_add_tag(filename, tag)
            if RE_EG_START.match(line):
                in_example = True

    def do_add_tag(self, filename, tag):
        if self._is_web_version and filename == "help.txt":
            htmlfilename = "/"
        else:
            htmlfilename = filename + ".html"
        self._urls[tag] = Link(filename, htmlfilename, tag)

    def sorted_tag_href_pairs(self):
        result = [
            (tag, link.href(is_same_doc=False)) for tag, link in self._urls.items()
        ]
        result.sort()
        return result

    def maplink(self, tag, curr_filename, css_class=None):
        links = self._urls.get(tag)
        if links is not None:
            is_pipe = css_class == "l"
            is_same_doc = links.filename == curr_filename
            return links.html(is_pipe, is_same_doc)
        elif css_class is not None:
            return f'<span class="{css_class}">{html_escape(tag)}</span>'
        else:
            return html_escape(tag)

    def to_html(self, filename, contents):
        out = []

        in_example = False
        is_help_txt = filename == "help.txt"
        faq_line = False
        for line in RE_NEWLINE.split(contents):
            line = line.rstrip("\r\n")
            line_tabs = line
            line = line.expandtabs()
            if RE_HRULE.match(line):
                out.extend(('<span class="h">', line, "</span>\n"))
                continue
            if in_example:
                if RE_EG_END.match(line):
                    in_example = False
                    if line[0] == "<":
                        line = line[1:]
                else:
                    out.extend(('<span class="e">', html_escape(line), "</span>\n"))
                    continue
            if RE_EG_START.match(line_tabs):
                in_example = True
                line = line[:-1]
            if RE_SECTION.match(line_tabs):
                m = RE_SECTION.match(line)
                out.extend(('<span class="c">', m.group(0), "</span>"))
                line = line[m.end() :]
            if (
                self._project is VimProject
                and is_help_txt
                and RE_LOCAL_ADD.match(line_tabs)
            ):
                faq_line = True
            lastpos = 0
            for match in RE_TAGWORD.finditer(line):
                pos = match.start()
                if pos > lastpos:
                    out.append(html_escape(line[lastpos:pos]))
                lastpos = match.end()
                # fmt: off
                (header, graphic, pipeword, starword, command, opt, ctrl, special,
                 title, note, url, word) = match.groups()
                # fmt: on
                if pipeword is not None:
                    out.append(self.maplink(pipeword, filename, "l"))
                elif starword is not None:
                    out.extend(
                        (
                            '<span id="',
                            urllib.parse.quote_plus(starword),
                            '" class="t">',
                            html_escape(starword),
                            "</span>",
                        )
                    )
                elif command is not None:
                    out.extend(('<span class="e">', html_escape(command), "</span>"))
                elif opt is not None:
                    out.append(self.maplink(opt, filename, "o"))
                elif ctrl is not None:
                    out.append(self.maplink(ctrl, filename, "k"))
                elif special is not None:
                    out.append(self.maplink(special, filename, "s"))
                elif title is not None:
                    out.extend(('<span class="i">', html_escape(title), "</span>"))
                elif note is not None:
                    out.extend(('<span class="n">', html_escape(note), "</span>"))
                elif header is not None:
                    out.extend(
                        ('<span class="h">', html_escape(header[:-1]), "</span>")
                    )
                elif graphic is not None:
                    out.append(html_escape(graphic[:-2]))
                elif url is not None:
                    out.extend(
                        ('<a class="u" href="', url, '">', html_escape(url), "</a>")
                    )
                elif word is not None:
                    out.append(self.maplink(word, filename))
            if lastpos < len(line):
                out.append(html_escape(line[lastpos:]))
            out.append("\n")
            if faq_line:
                out.append(FAQ_LINE)
                faq_line = False

        header = [
            HEAD_FMT.format(
                project=self._project,
                filename=filename,
            )
        ]

        if self._is_web_version:
            header.append(SEARCH_HEADERS)

        header.append(HEAD_END)

        if self._is_web_version and is_help_txt:
            header.append(
                INTRO_FMT.format(project=self._project, version=self._version)
            )

        sitenavi_links_fmt = self._project.sitenavi_links_fmt
        if self._is_web_version:
            sitenavi_links = sitenavi_links_fmt.format(helptxt="./")
            header.append(
                SITENAVI_SEARCH_FMT.format(
                    project=self._project, sitenavi_links=sitenavi_links
                )
            )
            sitenavi_footer = f"<p>{sitenavi_links}</p>"
        else:
            sitenavi_links = sitenavi_links_fmt.format(helptxt="help.txt.html")
            sitenavi = f"<p>{sitenavi_links}</p>"
            header.append(sitenavi)
            sitenavi_footer = sitenavi

        header.append(TEXTSTART)

        return "".join(chain(header, out, (FOOTER, sitenavi_footer, FOOTER2)))


@functools.cache
def html_escape(s):
    return html.escape(s, quote=False)
