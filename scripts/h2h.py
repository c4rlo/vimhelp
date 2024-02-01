#!/usr/bin/env .venv/bin/python3

# This script is meant to be run from the top-level directory of the
# repository, as 'scripts/h2h.py'. The virtualenv must already exist
# (use "inv venv" to create it).

import argparse
import os.path
import pathlib
import sys

import flask

root_path = pathlib.Path(__file__).parent.parent

sys.path.append(str(root_path))

from vimhelp.vimh2h import VimH2H  # noqa: E402


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
        "--project",
        "-p",
        choices=("vim", "neovim"),
        default="vim",
        help="Vim flavour (default: vim)",
    )
    parser.add_argument(
        "--web-version",
        "-w",
        action="store_true",
        help="Generate the web version of the files (default: offline version)",
    )
    parser.add_argument(
        "--theme",
        "-t",
        choices=("light", "dark"),
        help="Color theme (default: OS-native)",
    )
    parser.add_argument(
        "--no-tags",
        "-T",
        action="store_true",
        help="Ignore any tags file, always recreate tags from scratch",
    )
    parser.add_argument(
        "--profile", "-P", action="store_true", help="Profile performance"
    )
    parser.add_argument(
        "basenames", nargs="*", help="List of files to process (default: all)"
    )
    args = parser.parse_args()

    app = flask.Flask(
        __name__,
        root_path=pathlib.Path(__file__).resolve().parent,
        template_folder="../vimhelp/templates",
    )
    app.jinja_options["trim_blocks"] = True
    app.jinja_options["lstrip_blocks"] = True
    app.jinja_env.filters["static_path"] = lambda p: p

    with app.app_context():
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

    prelude = VimH2H.prelude(theme=args.theme)

    mode = "hybrid" if args.web_version else "offline"

    if not args.no_tags and (tags_file := args.in_dir / "tags").is_file():
        print("Processing tags file...")
        h2h = VimH2H(mode=mode, project=args.project, tags=tags_file.read_text())
        faq = args.in_dir / "vim_faq.txt"
        if faq.is_file():
            print("Processing FAQ tags...")
            h2h.add_tags(faq.name, faq.read_text())
    else:
        print("Initializing tags...")
        h2h = VimH2H(mode=mode, project=args.project)
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
            with (args.out_dir / f"{infile.name}.html").open("w") as f:
                f.write(prelude)
                f.write(html)

    if args.out_dir is not None:
        print("Symlinking/creating static files...")
        static_dir = root_path / "vimhelp" / "static"
        static_dir_rel = os.path.relpath(static_dir, args.out_dir)
        for target in static_dir.iterdir():
            target_name = target.name
            src = args.out_dir / target_name
            src.unlink(missing_ok=True)
            src.symlink_to(f"{static_dir_rel}/{target_name}")
        for name in "vimhelp.css", "vimhelp.js":
            content = flask.render_template(name, mode=mode)
            (args.out_dir / name).write_text(content)

    print("Done.")


main()
