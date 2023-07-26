# Translates Vim documentation to HTML

import functools
import html
import re
import urllib.parse

import flask
import markupsafe


class VimProject:
    name = "Vim"
    contrasted_name = "the original Vim"
    url = "https://www.vim.org/"
    vimdoc_site = "vimhelp.org"
    doc_src_url = "https://github.com/vim/vim/tree/master/runtime/doc"
    favicon_notice = "favicon is based on http://amnoid.de/tmp/vim_solidbright_512.png and is used with permission by its author"


class NeovimProject:
    name = "Neovim"
    contrasted_name = "Neovim"
    url = "https://neovim.io/"
    vimdoc_site = "neo.vimhelp.org"
    doc_src_url = "https://github.com/neovim/neovim/tree/master/runtime/doc"
    favicon_notice = "favicon taken from https://neovim.io/favicon.ico, which is licensed under CC-BY-3.0: https://creativecommons.org/licenses/by/3.0/"


VimProject.other = NeovimProject
NeovimProject.other = VimProject


PROJECTS = {"vim": VimProject, "neovim": NeovimProject}

FAQ_LINE = '<a href="vim_faq.txt.html#vim_faq.txt" class="l">vim_faq.txt</a>\tFrequently Asked Questions\n'
MATCHIT_LINE = '<a href="matchit.txt.html#matchit.txt" class="l">matchit.txt</a>\tExtended "%" matching\n'

RE_TAGLINE = re.compile(r"(\S+)\s+(\S+)")

PAT_WORDCHAR = "[!#-)+-{}~\xC0-\xFF]"

PAT_HEADER = r"(^.*~$)"
PAT_GRAPHIC = r"(^.* `$)"
PAT_PIPEWORD = r"(?<!\\)\|([#-)!+-{}~]+)\|"
PAT_STARWORD = r"\*([#-)!+-~]+)\*(?:(?=\s)|$)"
PAT_COMMAND = r"`([^` \t]+)`"
PAT_OPTWORD = r"('(?:[a-z]{2,}|t_..)')"
PAT_CTRL = r"((?:CTRL(?:-SHIFT)?|META|ALT)-(?:W_)?(?:\{char\}|<[A-Za-z]+?>|.)?)"
PAT_SPECIAL = (
    r"(<(?:[-a-zA-Z0-9_]+|[SCM]-.)>|\{.+?}|"
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
RE_HRULE = re.compile(r"(?:===.*===|---.*---)$")
RE_HRULE1 = re.compile(r"===.*===$")
RE_HEADING = re.compile(
    r"[0-9.\s*]*"
    r"(?!\s*vim:|\s*Next chapter:|\s*Copyright:|\s*Table of contents:|\s*Advance information about|$)"
    r"(.+?)\s*(?:\*|~?$)"
)
RE_EG_START = re.compile(r"(.* )?>(?:vim|lua)?$")
RE_EG_END = re.compile(r"[^ \t]")
RE_SECTION = re.compile(
    r"(?!NOTE$|UTF-8.$|VALID.$|OLE.$|CTRL-|\.\.\.$)"
    r"([A-Z.][-A-Z0-9 .,()_?]*?)\s*(?:\s\*|$)"
)
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

    @functools.cache  # noqa: B019
    def href(self, is_same_doc):
        if self._tag_quoted is None:
            return self._htmlfilename
        doc = "" if is_same_doc else self._htmlfilename
        return f"{doc}#{self._tag_quoted}"

    @functools.cache  # noqa: B019
    def html(self, is_pipe, is_same_doc):
        cssclass = "l" if is_pipe else self._cssclass
        return (
            f'<a href="{self.href(is_same_doc)}" class="{cssclass}">'
            f"{self._tag_escaped}</a>"
        )


# Concealed chars in Vim still count towards hard tabs' spacing calculations even though
# they are hidden. We need to count them so we can insert that many spaces before we
# encounter a hard tab to nudge it to the right position. This class helps with that.
class TabFixer:
    def __init__(self):
        self._accum_concealed_chars = 0

    def incr_concealed_chars(self, num):
        self._accum_concealed_chars += num

    def fix_tabs(self, text):
        if self._accum_concealed_chars > 0:
            if (tab_index := text.find("\t")) != -1:
                adjustment = " " * self._accum_concealed_chars
                self._accum_concealed_chars = 0
                return f"{text[:tab_index]}{adjustment}{text[tab_index:]}"
        return text


class VimH2H:
    def __init__(self, mode="online", project="vim", version=None, tags=None):
        self._mode = mode
        self._project = PROJECTS[project]
        self._version = version
        self._urls = {}
        if tags is not None:
            for line in RE_NEWLINE.split(tags):
                if m := RE_TAGLINE.match(line):
                    tag, filename = m.group(1, 2)
                    self.do_add_tag(filename, tag)
        self._urls["help-tags"] = Link("tags", "tags.html", "help-tags")

    def __del__(self):
        Link.href.cache_clear()
        Link.html.cache_clear()

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
        if self._mode == "online" and filename == "help.txt":
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

    def synthesize_tag(self, curr_filename, text):
        def xform(c):
            if c.isalnum():
                return c.lower()
            elif c in " ,.?!'\"":
                return "-"
            else:
                return ""

        base_tag = "_" + "".join(map(xform, text[:25]))
        tag = base_tag
        i = 0
        while True:
            link = self._urls.get(tag)
            if link is None or link.filename != curr_filename:
                return tag
            tag = f"{base_tag}_{i}"
            i += 1

    @staticmethod
    def prelude(theme):
        return flask.render_template("prelude.html", theme=theme)

    def to_html(self, filename, contents):
        is_help_txt = filename == "help.txt"
        lines = [line.rstrip("\r\n") for line in RE_NEWLINE.split(contents)]

        out = []
        sidebar_headings = []
        sidebar_lvl = 2
        in_example = False
        for idx, line in enumerate(lines):
            prev_line = "" if idx == 0 else lines[idx - 1]
            if prev_line == "" and idx > 1:
                prev_line = lines[idx - 2]

            if in_example:
                if RE_EG_END.match(line):
                    in_example = False
                    if line[0] == "<":
                        line = line[1:]
                else:
                    out.extend(('<span class="e">', html_escape(line), "</span>\n"))
                    continue

            if RE_HRULE.match(line):
                out.extend(('<span class="h">', html_escape(line), "</span>\n"))
                continue

            if m := RE_EG_START.match(line):
                in_example = True
                line = m.group(1) or ""

            heading = None
            skip_to_col = None
            if m := RE_SECTION.match(line):
                heading = m.group(1)
                heading_lvl = 2
                out.extend(('<span class="c">', heading, "</span>"))
                skip_to_col = m.end(1)
            elif RE_HRULE1.match(prev_line) and (m := RE_HEADING.match(line)):
                heading = m.group(1)
                heading_lvl = 1

            span_opened = False
            if heading is not None and sidebar_lvl >= heading_lvl:
                if sidebar_lvl > heading_lvl:
                    sidebar_lvl = heading_lvl
                    sidebar_headings = []
                if m := RE_STARTAG.search(line):
                    tag = m.group(1)
                else:
                    tag = self.synthesize_tag(filename, heading)
                    out.append(f'<span id="{tag}">')
                    span_opened = True
                tag_escaped = urllib.parse.quote_plus(tag)
                sidebar_headings.append(
                    markupsafe.Markup(
                        f'<a href="#{tag_escaped}">{html_escape(heading)}</a>'
                    )
                )

            if skip_to_col is not None:
                line = line[skip_to_col:]

            is_local_additions = is_help_txt and RE_LOCAL_ADD.match(line)
            lastpos = 0

            tab_fixer = TabFixer()

            for match in RE_TAGWORD.finditer(line):
                pos = match.start()
                if pos > lastpos:
                    out.append(html_escape(tab_fixer.fix_tabs(line[lastpos:pos])))
                lastpos = match.end()
                # fmt: off
                (header, graphic, pipeword, starword, command, opt, ctrl, special,
                 title, note, url, word) = match.groups()
                # fmt: on
                if pipeword is not None:
                    out.append(self.maplink(pipeword, filename, "l"))
                    tab_fixer.incr_concealed_chars(2)
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
                    tab_fixer.incr_concealed_chars(2)
                elif command is not None:
                    out.extend(('<span class="e">', html_escape(command), "</span>"))
                    tab_fixer.incr_concealed_chars(2)
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
                out.append(html_escape(tab_fixer.fix_tabs(line[lastpos:])))
            if span_opened:
                out.append("</span>")
            out.append("\n")

            if is_local_additions and self._project is VimProject:
                out.append(MATCHIT_LINE)
                out.append(FAQ_LINE)

        static_dir = "/" if self._mode == "online" else ""
        helptxt = "./" if self._mode == "online" else "help.txt.html"

        return flask.render_template(
            "page.html",
            mode=self._mode,
            project=self._project,
            version=self._version,
            filename=filename,
            static_dir=static_dir,
            helptxt=helptxt,
            content=markupsafe.Markup("".join(out)),
            sidebar_headings=sidebar_headings,
        )


@functools.cache
def html_escape(s):
    return html.escape(s, quote=False)
