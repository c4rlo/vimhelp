# converts vim documentation to html

import re
import urllib.parse
from itertools import chain

HEAD = """\
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
    "http://www.w3.org/TR/html4/loose.dtd">
<html>
<head>
<meta http-equiv="Content-type" content="text/html; charset={encoding}"/>
<title>Vim: {filename}</title>
<link rel="shortcut icon" href="favicon.ico">
<!-- favicon is based on http://amnoid.de/tmp/vim_solidbright_512.png and is used with permission by its author -->
<!--[if IE]>
<link rel="stylesheet" href="vimhelp-ie.css" type="text/css">
<![endif]-->
<!--[if !IE]>-->
<link rel="stylesheet" href="vimhelp.css" type="text/css">
<!--<![endif]-->
"""

SEARCH_SCRIPT = """
<script>
  (function() {
    var gcse = document.createElement('script'); gcse.type = 'text/javascript'; gcse.async = true;
    gcse.src = (document.location.protocol == 'https:' ? 'https:' : 'http:') +
        '//cse.google.com/cse.js?cx=007529716539815883269:a71bug8rd0k';
    var s = document.getElementsByTagName('script')[0]; s.parentNode.insertBefore(gcse, s);
  })();
</script>
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
href="https://github.com/chrisbra/vim_faq" target="_blank" class="d">github
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

SITENAVI_PLAIN = '<p>' + SITENAVI_LINKS_PLAIN + '</p>'
SITENAVI_WEB = '<p>' + SITENAVI_LINKS_WEB + '</p>'

SITENAVI_SEARCH = '<table width="100%"><tbody><tr><td>' + SITENAVI_LINKS_WEB + \
    '</td><td style="text-align: right; max-width: 25vw">' \
    '<div class="gcse-searchbox"></div></td></tr></tbody></table>' \
    '<div class="gcse-searchresults"></div>'

TEXTSTART = """
<div id="d1">
<pre id="sp">                                                                                </pre>
<div id="d2">
<pre>
"""

FOOTER = '</pre>'

FOOTER2 = """
<p id="footer">This site is maintained by Carlo Teubner (<i>(my first name) at cteubner dot net</i>).</p>
</div>
</div>
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
    __slots__ = 'link_plain_same',    'link_pipe_same', \
                'link_plain_foreign', 'link_pipe_foreign', \
                'filename'

    def __init__(self, link_plain_same, link_plain_foreign,
                 link_pipe_same,  link_pipe_foreign, filename):
        self.link_plain_same    = link_plain_same
        self.link_plain_foreign = link_plain_foreign
        self.link_pipe_same     = link_pipe_same
        self.link_pipe_foreign  = link_pipe_foreign
        self.filename           = filename


class VimH2H:
    def __init__(self, tags, version=None, is_web_version=True):
        self._urls = {}
        self._version = version
        self._is_web_version = is_web_version
        for line in RE_NEWLINE.split(tags):
            m = RE_TAGLINE.match(line)
            if m:
                tag, filename = m.group(1, 2)
                self.do_add_tag(filename, tag)

    def add_tags(self, filename, contents):
        for match in RE_STARTAG.finditer(contents):
            tag = match.group(1).replace('\\', '\\\\').replace('/', '\\/')
            self.do_add_tag(str(filename), tag)

    def do_add_tag(self, filename, tag):
        tag_quoted = urllib.parse.quote_plus(tag)

        def mkpart1(doc):
            return '<a href="' + doc + '#' + tag_quoted + '" class="'

        part1_same = mkpart1('')
        if self._is_web_version and filename == 'help.txt':
            doc = '/'
        else:
            doc = filename + '.html'
        part1_foreign = mkpart1(doc)
        part2 = '">' + html_escape[tag] + '</a>'

        def mklinks(cssclass):
            return (part1_same    + cssclass + part2,
                    part1_foreign + cssclass + part2)

        cssclass_plain = 'd'
        m = RE_LINKWORD.match(tag)
        if m:
            opt, ctrl, special = m.groups()
            if opt       is not None: cssclass_plain = 'o'
            elif ctrl    is not None: cssclass_plain = 'k'
            elif special is not None: cssclass_plain = 's'
        links_plain = mklinks(cssclass_plain)
        links_pipe = mklinks('l')
        self._urls[tag] = Link(
            links_plain[0], links_plain[1],
            links_pipe[0],  links_pipe[1],
            filename)

    def maplink(self, tag, curr_filename, css_class=None):
        links = self._urls.get(tag)
        if links is not None:
            if links.filename == curr_filename:
                if css_class == 'l': return links.link_pipe_same
                else:                return links.link_plain_same
            else:
                if css_class == 'l': return links.link_pipe_foreign
                else:                return links.link_plain_foreign
        elif css_class is not None:
            return '<span class="' + css_class + '">' + html_escape[tag] + \
                    '</span>'
        else:
            return html_escape[tag]

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
                    out.extend(('<span class="e">', html_escape[line],
                               '</span>\n'))
                    continue
            if RE_EG_START.match(line_tabs):
                inexample = 1
                line = line[0:-1]
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
                    out.append(html_escape[line[lastpos:pos]])
                lastpos = match.end()
                header, graphic, pipeword, starword, command, opt, ctrl, \
                    special, title, note, url, word = match.groups()
                if pipeword is not None:
                    out.append(self.maplink(pipeword, filename, 'l'))
                elif starword is not None:
                    out.extend(('<a name="', urllib.parse.quote_plus(starword),
                                '" class="t">', html_escape[starword], '</a>'))
                elif command is not None:
                    out.extend(('<span class="e">', html_escape[command],
                                '</span>'))
                elif opt is not None:
                    out.append(self.maplink(opt, filename, 'o'))
                elif ctrl is not None:
                    out.append(self.maplink(ctrl, filename, 'k'))
                elif special is not None:
                    out.append(self.maplink(special, filename, 's'))
                elif title is not None:
                    out.extend(('<span class="i">', html_escape[title],
                                '</span>'))
                elif note is not None:
                    out.extend(('<span class="n">', html_escape[note],
                                '</span>'))
                elif header is not None:
                    out.extend(('<span class="h">', html_escape[header[:-1]],
                                '</span>'))
                elif graphic is not None:
                    out.append(html_escape[graphic[:-2]])
                elif url is not None:
                    out.extend(('<a class="u" href="', url, '">' +
                                html_escape[url], '</a>'))
                elif word is not None:
                    out.append(self.maplink(word, filename))
            if lastpos < len(line):
                out.append(html_escape[line[lastpos:]])
            out.append('\n')
            if inexample == 1:
                inexample = 2
            if faq_line:
                out.append(VIM_FAQ_LINE)
                faq_line = False

        header = []
        header.append(HEAD.format(encoding=encoding, filename=filename))
        if self._is_web_version:
            header.append(SEARCH_SCRIPT)
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


class HtmlEscCache(dict):
    def __missing__(self, key):
        r = key.replace('&', '&amp;') \
               .replace('<', '&lt;') \
               .replace('>', '&gt;')
        self[key] = r
        return r


html_escape = HtmlEscCache()
