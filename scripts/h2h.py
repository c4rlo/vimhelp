#!/usr/bin/python2

import sys, os, os.path
#import cProfile

sys.path.append('../gae')

from vimh2h import VimH2H

def slurp(filename):
    f = open(filename)
    c = f.read()
    f.close()
    return c

def usage():
    return "usage: " + sys.argv[0] + " IN_DIR OUT_DIR [BASENAMES...]"

def main():
    if len(sys.argv) < 3: sys.exit(usage())

    in_dir = sys.argv[1]
    out_dir = sys.argv[2]
    basenames = sys.argv[3:]

    print "Processing tags..."
    h2h = VimH2H(slurp(os.path.join(in_dir, 'tags')))

    if len(basenames) == 0:
        basenames = os.listdir(in_dir)

    for basename in basenames:
        if os.path.splitext(basename)[1] != '.txt' and basename != 'tags':
            print "Ignoring " + basename
            continue
        print "Processing " + basename + "..."
        path = os.path.join(in_dir, basename)
        text = slurp(path)
        try:
            text.decode('UTF-8')
        except UnicodeError:
            encoding = 'ISO-8859-1'
        else:
            encoding = 'UTF-8'
        outpath = os.path.join(out_dir, basename + '.html')
        of = open(outpath, 'w')
        of.write(h2h.to_html(basename, slurp(path), encoding,
                             web_version=False))
        of.close()

main()
#cProfile.run('main()')
