#!/usr/bin/env python3

import argparse
import pathlib
import sys

sys.path.append(".")

from vimhelp.vimh2h import VimH2H  # noqa: E402


def slurp(filename):
    f = open(filename, "rb")
    c = f.read()
    f.close()
    return c


def usage():
    return "usage: " + sys.argv[0] + " IN_DIR OUT_DIR [BASENAMES...]"


def main():
    parser = argparse.ArgumentParser(description="Convert Vim help files to HTML")
    parser.add_argument(
        "--in-dir",
        "-i",
        required=True,
        type=pathlib.Path,
        help="Directory of Vim doc files",
    )
    parser.add_argument(
        "--out-dir",
        "-o",
        type=pathlib.Path,
        help="Output directory (omit for no output)",
    )
    parser.add_argument(
        "--no-tags",
        "-T",
        action="store_true",
        help="Ignore any tags file, always recreate tags from " "scratch",
    )
    parser.add_argument(
        "--profile", "-p", action="store_true", help="Profile performance"
    )
    parser.add_argument(
        "basenames", nargs="*", help="List of files to process (default: all)"
    )
    args = parser.parse_args()

    if args.profile:
        import cProfile
        import pstats

        with cProfile.Profile() as pr:
            run(args)
        stats = pstats.Stats(pr).sort_stats("cumulative")
        stats.print_stats()
    else:
        run(args)


def run(args):
    if not args.in_dir.is_dir():
        raise RuntimeError(f"{args.in_dir} is not a directory")

    if not args.no_tags and (tags_file := args.in_dir / "tags").is_file():
        print("Processing tags file...")
        h2h = VimH2H(tags_file.read_text(), is_web_version=False)
        faq = args.in_dir / "vim_faq.txt"
        if faq.is_file():
            print("Processing FAQ tags...")
            h2h.add_tags(faq.name, faq.read_text())
    else:
        print("Initializing tags...")
        h2h = VimH2H("", is_web_version=False)
        for infile in args.in_dir.iterdir():
            if infile.suffix == ".txt":
                h2h.add_tags(infile.name, infile.read_text())

    if args.out_dir is not None:
        args.out_dir.mkdir(exist_ok=True)

    for infile in args.in_dir.iterdir():
        if len(args.basenames) != 0 and infile.name not in args.basenames:
            continue
        if infile.suffix != ".txt" and infile.name != "tags":
            print(f"Ignoring {infile}")
            continue
        content = infile.read_text()
        print(f"Processing {infile}...")
        html = h2h.to_html(infile.name, content)
        if args.out_dir is not None:
            (args.out_dir / f"{infile.name}.html").write_text(html)


main()
