# converts vim documentation to html

import sys
import re
import cgi
import urllib
from itertools import chain

CONTENT_TYPE = "Content-Type: text/html; charset={charset}\n\n"

HEADER1 = """\
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
<title>Vim: {filename}</title>
<!--[if IE]>
<link rel="stylesheet" href="vimhelp-ie.css" type="text/css">
<![endif]-->
<!--[if !IE]>-->
<link rel="stylesheet" href="vimhelp.css" type="text/css">
<!--<![endif]-->
</head>
<body>
"""

START_HEADER = """
<h1>Vim help files</h1>
<p>This is an HTML version of the <a href="http://www.vim.org/"
target="_blank">Vim</a> help pages. They are kept up-to-date automatically from
the <a href="http://code.google.com/p/vim/source/browse/runtime/doc"
target="_blank" class="d">Vim source repository</a>. Also included is the <a
href="vim_faq.txt.html">Vim FAQ</a>, kept up to date from its <a
href="http://github.com/chrisbra/vim_faq" target="_blank" class="d">github
repository</a>.</p>
"""

SITENAVI = """
<p>
Quick links:
<a href="/">help overview</a> &middot;
<a href="quickref.txt.html">quick reference</a> &middot;
<a href="usr_toc.txt.html">user manual toc</a> &middot;
<a href="help.txt.html#reference_toc">reference manual toc</a> &middot;
<a href="vim_faq.txt.html">faq</a>
</p>
"""

SITESEARCH = """
<div id="cse" style="width: 100%;">Loading Google custom search</div>
<script src="http://www.google.com/jsapi" type="text/javascript"></script>
<script type="text/javascript">
  google.load('search', '1', {language : 'en'});
  google.setOnLoadCallback(function() {
    var customSearchControl = new google.search.CustomSearchControl('007529716539815883269:a71bug8rd0k');
    customSearchControl.setResultSetSize(google.search.Search.FILTERED_CSE_RESULTSET);
    customSearchControl.draw('cse');
  }, true);
</script>
"""

HEADER2 = """
<div id="d1">
<pre id="sp">                                                                                </pre>
<div id="d2">
<pre>
"""

FOOTER = '</pre>'

FOOTER2 = """
<p id="footer">This site is maintained by Carlo Teubner (<i>(my first name) dot (my last name) at gmail dot com</i>).</p>
</div>
</div>
</body>
</html>
"""

VIM_FAQ_LINE = '<a href="vim_faq.txt.html#vim_faq.txt" class="l">' \
	       'vim_faq.txt</a>   Frequently Asked Questions\n'

RE_TAGLINE = re.compile(r'(\S+)\s+(\S+)')

PAT_HEADER   = r'(?P<header>^.*~$)'
PAT_GRAPHIC  = r'(?P<graphic>^.* `$)'
PAT_PIPEWORD = r'(?P<pipe>(?<!\\)\|[#-)!+-~]+\|)'
PAT_STARWORD = r'(?P<star>\*[#-)!+-~]+\*(?:(?=\s)|$))'
PAT_OPTWORD  = r"(?P<opt>'(?:[a-z]{2,}|t_..)')"
PAT_CTRL     = r'(?P<ctrl>CTRL-(?:W_)?(?:[\w\[\]^+-<>=@]|<[A-Za-z]+?>)?)'
PAT_SPECIAL  = r'(?P<special><.*?>|\{.*?}|' + \
	       r'\[(?:range|line|count|offset|\+?cmd|[-+]?num|\+\+opt|' + \
	       r'arg|arguments|ident|addr|group)]|' + \
	       r'(?<=\s)\[[-a-z^A-Z0-9_]{2,}])'
PAT_TITLE    = r'(?P<title>Vim version [0-9.a-z]+|VIM REFERENCE.*)'
PAT_NOTE     = r'(?P<note>Notes?:?)'
PAT_URL      = r'(?P<url>(?:https?|ftp)://[^\'"<> \t]+[a-zA-Z0-9/])'
PAT_WORD     = r'(?P<word>[!#-)+-{}~]+)'
RE_LINKWORD = re.compile(
	PAT_OPTWORD  + '|' + \
	PAT_CTRL     + '|' + \
	PAT_SPECIAL)
RE_TAGWORD = re.compile(
	PAT_HEADER   + '|' + \
        PAT_GRAPHIC  + '|' + \
	PAT_PIPEWORD + '|' + \
	PAT_STARWORD + '|' + \
	PAT_OPTWORD  + '|' + \
	PAT_CTRL     + '|' + \
	PAT_SPECIAL  + '|' + \
	PAT_TITLE    + '|' + \
	PAT_NOTE     + '|' + \
	PAT_URL      + '|' + \
	PAT_WORD)
RE_NEWLINE   = re.compile(r'[\r\n]')
RE_HRULE     = re.compile(r'[-=]{3,}.*[-=]{3,3}$')
RE_EG_START  = re.compile(r'(?:.* )?>$')
RE_EG_END    = re.compile(r'\S')
RE_SECTION   = re.compile(r'[-A-Z .][-A-Z0-9 .()]*(?=\s+\*)')
RE_STARTAG   = re.compile(r'\s\*([^ \t|]+)\*(?:\s|$)')
RE_LOCAL_ADD = re.compile(r'LOCAL ADDITIONS:\s+\*local-additions\*$')

class Link:
    def __init__(self, link_pipe, link_plain):
	self.link_pipe = link_pipe
	self.link_plain = link_plain

class VimH2H:
    urls = { }

    def __init__(self, tags):
	for line in RE_NEWLINE.split(tags):
	    m = RE_TAGLINE.match(line)
	    if m:
		tag, filename = m.group(1, 2)
		self.do_add_tag(filename, tag)

    def add_tags(self, filename, contents):
	for match in RE_STARTAG.finditer(contents):
	    tag = match.group(1).replace('\\', '\\\\').replace('/', '\\/')
	    self.do_add_tag(filename, tag)

    def do_add_tag(self, filename, tag):
	part1 = '<a href="' + filename + '.html#' + \
		urllib.quote_plus(tag) + '"'
	part2 = '>' + cgi.escape(tag) + '</a>'
	link_pipe = part1 + ' class="l"' + part2
	classattr = ' class="d"'
	m = RE_LINKWORD.match(tag)
	if m:
	    opt, ctrl, special = m.group('opt', 'ctrl', 'special')
	    if opt is not None: classattr = ' class="o"'
	    elif ctrl is not None: classattr = ' class="k"'
	    elif special is not None: classattr = ' class="s"'
	link_plain = part1 + classattr + part2
	self.urls[tag] = Link(link_pipe, link_plain)

    def maplink(self, tag, css_class = None):
	links = self.urls.get(tag)
	if links is not None:
	    if css_class == 'l': return links.link_pipe
	    else: return links.link_plain
	elif css_class is not None:
	    return '<span class="' + css_class + '">' + cgi.escape(tag) + \
		    '</span>'
	else: return cgi.escape(tag)

    def to_html(self, filename, contents, encoding = None,
            include_sitesearch = True, include_faq = True):

	out = [ ]

	inexample = 0
        is_help_txt = (filename == 'help.txt')
	faq_line = False
	for line in RE_NEWLINE.split(contents):
	    line = line.rstrip('\r\n')
	    line_tabs = line
	    line = line.expandtabs()
	    if RE_HRULE.match(line):
		out.append('<span class="h">' + line + '</span>\n')
		continue
	    if inexample == 2:
		if RE_EG_END.match(line):
		    inexample = 0
		    if line[0] == '<': line = line[1:]
		else:
		    out.append('<span class="e">' + cgi.escape(line) +
			    '</span>\n')
		    continue
	    if RE_EG_START.match(line_tabs):
		inexample = 1
		line = line[0:-1]
	    if RE_SECTION.match(line_tabs):
		m = RE_SECTION.match(line)
		out.append(m.expand(r'<span class="c">\g<0></span>'))
		line = line[m.end():]
	    if is_help_txt and RE_LOCAL_ADD.match(line_tabs):
		faq_line = True
	    lastpos = 0
	    for match in RE_TAGWORD.finditer(line):
		pos = match.start()
		if pos > lastpos:
		    out.append(cgi.escape(line[lastpos:pos]))
		lastpos = match.end()
		pipeword, starword, opt, ctrl, special, title, note, \
			header, graphic, url, word = \
			match.group('pipe', 'star', 'opt', 'ctrl',
			'special', 'title', 'note', 'header', 'graphic', 'url', 'word')
		if pipeword is not None:
		    out.append(self.maplink(pipeword[1:-1], 'l'))
		elif starword is not None:
		    tag = starword[1:-1]
		    out.append('<a name="' + urllib.quote_plus(tag) +
			    '" class="t">' + cgi.escape(tag) + '</a>')
		elif opt is not None:
		    out.append(self.maplink(opt, 'o'))
		elif ctrl is not None:
		    out.append(self.maplink(ctrl, 'k'))
		elif special is not None:
		    out.append(self.maplink(special, 's'))
		elif title is not None:
		    out.append('<span class="i">' +
			    cgi.escape(title) + '</span>')
		elif note is not None:
		    out.append('<span class="n">' +
			    cgi.escape(note) + '</span>')
		elif header is not None:
		    out.append('<span class="h">' +
			    cgi.escape(header[:-1]) + '</span>')
                elif graphic is not None:
                    out.append(cgi.escape(graphic[:-2]))
		elif url is not None:
		    out.append('<a class="u" href="' + url + '">' +
			    cgi.escape(url) + '</a>')
		elif word is not None:
		    out.append(self.maplink(word))
	    if lastpos < len(line):
		out.append(cgi.escape(line[lastpos:]))
	    out.append('\n')
	    if inexample == 1: inexample = 2
	    if faq_line:
		out.append(VIM_FAQ_LINE)
		faq_line = False

        header = []
        if encoding is not None:
            header.append(CONTENT_TYPE.replace('{charset}', encoding))
        header.append(HEADER1.replace('{filename}', filename))
        if is_help_txt:
            header.append(START_HEADER)
        header.append(SITENAVI)
        if include_sitesearch:
            header.append(SITESEARCH)
        header.append(HEADER2)
        return ''.join(chain(header, out, (FOOTER, SITENAVI, FOOTER2)))

