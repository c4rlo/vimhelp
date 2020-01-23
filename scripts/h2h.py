#!/usr/bin/env python3

import sys
import os
import os.path
# import cProfile

sys.path.append('.')

from vimhelp.vimh2h import VimH2H  # noqa: E402


def slurp(filename):
    f = open(filename, 'rb')
    c = f.read()
    f.close()
    return c


def usage():
    return "usage: " + sys.argv[0] + " IN_DIR OUT_DIR [BASENAMES...]"


def main():
    if len(sys.argv) < 3:
        sys.exit(usage())

    in_dir = sys.argv[1]
    out_dir = sys.argv[2]
    basenames = sys.argv[3:]

    print("Processing tags...")
    h2h = VimH2H(slurp(os.path.join(in_dir, 'tags')).decode(),
                 is_web_version=False)

    if len(basenames) == 0:
        basenames = os.listdir(in_dir)

    for basename in basenames:
        if os.path.splitext(basename)[1] != '.txt' and basename != 'tags':
            print("Ignoring " + basename)
            continue
        print("Processing " + basename + "...")
        path = os.path.join(in_dir, basename)
        content = slurp(path)
        try:
            encoding = 'UTF-8'
            content_str = content.decode(encoding)
        except UnicodeError:
            encoding = 'ISO-8859-1'
            content_str = content.decode(encoding)
        outpath = os.path.join(out_dir, basename + '.html')
        of = open(outpath, 'wb')
        of.write(h2h.to_html(basename, content_str, encoding).encode())
        of.close()


main()
# cProfile.run('main()')
