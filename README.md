# vimhelp.org

This is the code behind the https://vimhelp.org website. It runs on
[Google App Engine](https://cloud.google.com/appengine/).

To make testing and deploying easier, common project tasks are defined in
`justfile` for use with [_just_](https://just.systems/). Run `just --list`
to see the available recipes.

## Generating static pages

To generate static HTML pages instead of running on Google App Engine:

1. Make sure you have [uv](https://docs.astral.sh/uv/).
2. Run the following from the repository root (replace the `-i` parameter
   with the Vim documentation location on your computer):
   ```
   scripts/h2h.py -i /usr/share/vim/vim92/doc/ -o html/
   ```
   uv creates or updates the project environment automatically.
   The script offers a few options; run with `-h` to see what is available.

## License

This code is made freely available under the MIT License (see file LICENSE).
