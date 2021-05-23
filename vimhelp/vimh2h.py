# converts vim documentation to html

import functools
import html
import re
import urllib.parse
from itertools import chain

HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="{encoding}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Vim help pages, always up-to-date">
<title>Vim: {filename}</title>
<link rel="shortcut icon" href="favicon.ico">
<!-- favicon is based on http://amnoid.de/tmp/vim_solidbright_512.png and is used with permission by its author -->
<link rel="stylesheet" href="vimhelp.css" type="text/css">
"""

SEARCH_HEADERS = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" integrity="sha256-zaSoHBhwFdle0scfGEFUCwggPN7F+ip9XRglo8IWb4w=" crossorigin="anonymous">
<script defer src="https://cdn.jsdelivr.net/npm/jquery@3.5.1/dist/jquery.min.js" integrity="sha256-9/aliU8dGd2tb6OSsuzixeV4y/faTqgFtohetphbbj0=" crossorigin="anonymous"></script>
<script defer src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js" integrity="sha256-9yRP/2EFlblE92vzCA10469Ctd0jT48HnmmMw5rJZrA=" crossorigin="anonymous"></script>
<script defer src="vimhelp.js"></script>
"""

HEAD_END = '</head><body>'

INTRO = """
<h1>Vim help files</h1>
<p>This is an HTML version of the <a href="http://www.vim.org/"
target="_blank">Vim</a> help pages{vers-note}. They are kept up-to-date <a
href="https://github.com/c4rlo/vimhelp" target="_blank"
class="d">automatically</a> from the <a
href="https://github.com/vim/vim/tree/master/runtime/doc" target="_blank"
class="d">Vim source repository</a>. Also included is the <a
href="vim_faq.txt.html">Vim FAQ</a>, kept up to date from its <a
href="https://github.com/chrisbra/vim_faq" target="_blank" class="d">GitHub
repository</a>.</p>
"""

VERSION_NOTE = ", current as of Vim {version}"

SITENAVI_LINKS = """
Quick links:
<a href="/">help overview</a> &middot;
<a href="quickref.txt.html">quick reference</a> &middot;
<a href="usr_toc.txt.html">user manual toc</a> &middot;
<a href="{helptxt}#reference_toc">reference manual toc</a> &middot;
<a href="vim_faq.txt.html">faq</a>
"""

SITENAVI_LINKS_PLAIN = SITENAVI_LINKS.format(helptxt='help.txt.html')
SITENAVI_LINKS_WEB = SITENAVI_LINKS.format(helptxt='/')

SITENAVI_PLAIN = f'<p>{SITENAVI_LINKS_PLAIN}</p>'
SITENAVI_WEB = f'<p>{SITENAVI_LINKS_WEB}</p>'

SITENAVI_SEARCH = f"""
<div class="bar">
  <div class="ql">{SITENAVI_LINKS_WEB}</div>
  <div class="srch">
    <select id="vh-select-tag"></select>
  </div>
  <form class="srch" action="https://duckduckgo.com" method="get" target="_blank">
    <input type="hidden" name="sites" value="vimhelp.org">
    <input type="search" name="q" id="site-search-input" placeholder="Site search">
  </form>
</div>
"""

TEXTSTART = '<pre>'

FOOTER = '</pre>'

FOOTER2 = """
<footer>This site is maintained by Carlo Teubner (<i>(my first name) at cteubner dot net</i>).</footer>
</body>
</html>
"""

VIM_FAQ_LINE = '<a href="vim_faq.txt.html#vim_faq.txt" class="l">' \
               'vim_faq.txt</a>   Frequently Asked Questions\n'

RE_TAGLINE = re.compile(r'(\S+)\s+(\S+)')

PAT_WORDCHAR = '[!#-)+-{}~\xC0-\xFF]'

PAT_HEADER   = r'(^.*~$)'
PAT_GRAPHIC  = r'(^.* `$)'
PAT_PIPEWORD = r'(?<!\\)\|([#-)!+-~]+)\|'
PAT_STARWORD = r'\*([#-)!+-~]+)\*(?:(?=\s)|$)'
PAT_COMMAND  = r'`([^` ]+)`'
PAT_OPTWORD  = r"('(?:[a-z]{2,}|t_..)')"
PAT_CTRL     = r'(CTRL-(?:W_)?(?:\{char\}|<[A-Za-z]+?>|.)?)'
PAT_SPECIAL  = r'(<.+?>|\{.+?}|' \
               r'\[(?:range|line|count|offset|\+?cmd|[-+]?num|\+\+opt|' \
               r'arg|arguments|ident|addr|group)]|' \
               r'(?<=\s)\[[-a-z^A-Z0-9_]{2,}])'
PAT_TITLE    = r'(Vim version [0-9.a-z]+|VIM REFERENCE.*)'
PAT_NOTE     = r'((?<!' + PAT_WORDCHAR + r')(?:note|NOTE|Notes?):?' \
                 r'(?!' + PAT_WORDCHAR + r'))'
PAT_URL      = r'((?:https?|ftp)://[^\'"<> \t]+[a-zA-Z0-9/])'
PAT_WORD     = r'((?<!' + PAT_WORDCHAR + r')' + PAT_WORDCHAR + r'+' \
                 r'(?!' + PAT_WORDCHAR + r'))'

RE_LINKWORD = re.compile(
        PAT_OPTWORD  + '|' +
        PAT_CTRL     + '|' +
        PAT_SPECIAL)
RE_TAGWORD = re.compile(
        PAT_HEADER   + '|' +
        PAT_GRAPHIC  + '|' +
        PAT_PIPEWORD + '|' +
        PAT_STARWORD + '|' +
        PAT_COMMAND  + '|' +
        PAT_OPTWORD  + '|' +
        PAT_CTRL     + '|' +
        PAT_SPECIAL  + '|' +
        PAT_TITLE    + '|' +
        PAT_NOTE     + '|' +
        PAT_URL      + '|' +
        PAT_WORD)
RE_NEWLINE   = re.compile(r'[\r\n]')
RE_HRULE     = re.compile(r'[-=]{3,}.*[-=]{3,3}$')
RE_EG_START  = re.compile(r'(?:.* )?>$')
RE_EG_END    = re.compile(r'\S')
RE_SECTION   = re.compile(r'[-A-Z .][-A-Z0-9 .()]*(?=\s+\*)')
RE_STARTAG   = re.compile(r'\s\*([^ \t|]+)\*(?:\s|$)')
RE_LOCAL_ADD = re.compile(r'LOCAL ADDITIONS:\s+\*local-additions\*$')


class Link:
    def __init__(self, filename, htmlfilename, tag):
        self.filename = filename
        self._htmlfilename = htmlfilename
        self._tag_quoted = urllib.parse.quote_plus(tag)
        self._tag_escaped = html_escape(tag)
        self._cssclass = 'd'
        if m := RE_LINKWORD.match(tag):
            opt, ctrl, special = m.groups()
            if opt       is not None: self._cssclass = 'o'
            elif ctrl    is not None: self._cssclass = 'k'
            elif special is not None: self._cssclass = 's'

    @functools.cache
    def href(self, is_same_doc):
        doc = '' if is_same_doc else self._htmlfilename
        return f"{doc}#{self._tag_quoted}"

    @functools.cache
    def html(self, is_pipe, is_same_doc):
        cssclass = 'l' if is_pipe else self._cssclass
        return f'<a href="{self.href(is_same_doc)}" class="{cssclass}">' + \
               f'{self._tag_escaped}</a>'


class VimH2H:
    def __init__(self, tags, version=None, is_web_version=True):
        self._urls = {}
        self._version = version
        self._is_web_version = is_web_version
        for line in RE_NEWLINE.split(tags):
            if m := RE_TAGLINE.match(line):
                tag, filename = m.group(1, 2)
                self.do_add_tag(filename, tag)

    def add_tags(self, filename, contents):
        for match in RE_STARTAG.finditer(contents):
            tag = match.group(1).replace('\\', '\\\\').replace('/', '\\/')
            self.do_add_tag(str(filename), tag)

    def do_add_tag(self, filename, tag):
        if self._is_web_version and filename == 'help.txt':
            htmlfilename = '/'
        else:
            htmlfilename = filename + '.html'
        self._urls[tag] = Link(filename, htmlfilename, tag)

    def sorted_tag_href_pairs(self):
        result = [ (tag, link.href(is_same_doc=False))
                   for tag, link in self._urls.items() ]
        result.sort()
        return result

    def maplink(self, tag, curr_filename, css_class=None):
        links = self._urls.get(tag)
        if links is not None:
            is_pipe = css_class == 'l'
            is_same_doc = links.filename == curr_filename
            return links.html(is_pipe, is_same_doc)
        elif css_class is not None:
            return f'<span class="{css_class}">{html_escape(tag)}</span>'
        else:
            return html_escape(tag)

    def to_html(self, filename, contents, encoding):
        out = []

        inexample = 0
        filename = str(filename)
        is_help_txt = (filename == 'help.txt')
        faq_line = False
        for line in RE_NEWLINE.split(contents):
            line = line.rstrip('\r\n')
            line_tabs = line
            line = line.expandtabs()
            if RE_HRULE.match(line):
                out.extend(('<span class="h">', line, '</span>\n'))
                continue
            if inexample == 2:
                if RE_EG_END.match(line):
                    inexample = 0
                    if line[0] == '<':
                        line = line[1:]
                else:
                    out.extend(('<span class="e">', html_escape(line),
                               '</span>\n'))
                    continue
            if RE_EG_START.match(line_tabs):
                inexample = 1
                line = line[:-1]
            if RE_SECTION.match(line_tabs):
                m = RE_SECTION.match(line)
                out.extend((r'<span class="c">', m.group(0), r'</span>'))
                line = line[m.end():]
            if is_help_txt and RE_LOCAL_ADD.match(line_tabs):
                faq_line = True
            lastpos = 0
            for match in RE_TAGWORD.finditer(line):
                pos = match.start()
                if pos > lastpos:
                    out.append(html_escape(line[lastpos:pos]))
                lastpos = match.end()
                header, graphic, pipeword, starword, command, opt, ctrl, \
                    special, title, note, url, word = match.groups()
                if pipeword is not None:
                    out.append(self.maplink(pipeword, filename, 'l'))
                elif starword is not None:
                    out.extend(('<span id="', urllib.parse.quote_plus(starword),
                                '" class="t">', html_escape(starword), '</span>'))
                elif command is not None:
                    out.extend(('<span class="e">', html_escape(command),
                                '</span>'))
                elif opt is not None:
                    out.append(self.maplink(opt, filename, 'o'))
                elif ctrl is not None:
                    out.append(self.maplink(ctrl, filename, 'k'))
                elif special is not None:
                    out.append(self.maplink(special, filename, 's'))
                elif title is not None:
                    out.extend(('<span class="i">', html_escape(title),
                                '</span>'))
                elif note is not None:
                    out.extend(('<span class="n">', html_escape(note),
                                '</span>'))
                elif header is not None:
                    out.extend(('<span class="h">', html_escape(header[:-1]),
                                '</span>'))
                elif graphic is not None:
                    out.append(html_escape(graphic[:-2]))
                elif url is not None:
                    out.extend(('<a class="u" href="', url, '">', html_escape(url),
                                '</a>'))
                elif word is not None:
                    out.append(self.maplink(word, filename))
            if lastpos < len(line):
                out.append(html_escape(line[lastpos:]))
            out.append('\n')
            if inexample == 1:
                inexample = 2
            if faq_line:
                out.append(VIM_FAQ_LINE)
                faq_line = False

        header = []
        header.append(HEAD.format(encoding=encoding, filename=filename))
        if self._is_web_version:
            header.append(SEARCH_HEADERS)
        header.append(HEAD_END)
        if self._is_web_version and is_help_txt:
            vers_note = VERSION_NOTE.replace('{version}', self._version) \
                    if self._version else ''
            header.append(INTRO.replace('{vers-note}', vers_note))
        if self._is_web_version:
            header.append(SITENAVI_SEARCH)
            sitenavi_footer = SITENAVI_WEB
        else:
            header.append(SITENAVI_PLAIN)
            sitenavi_footer = SITENAVI_PLAIN
        header.append(TEXTSTART)
        return ''.join(chain(header, out, (FOOTER, sitenavi_footer, FOOTER2)))


@functools.cache
def html_escape(s):
    return html.escape(s, quote=False)
