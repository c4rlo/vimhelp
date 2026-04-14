# vimhelp.org

This is the code behind the https://vimhelp.org website. It runs on
[Google App Engine](https://cloud.google.com/appengine/).

To make testing and deploying easier, a `tasks.py` file exists for use
with the [_Invoke_](https://www.pyinvoke.org/) tool (which is similar in
spirit to _Make_).

## Generating static pages

To generate static HTML pages instead of running on Google App Engine:

- Make sure you have [uv](https://docs.astral.sh/uv/), and run `uv sync`
  to create/update a virtualenv in `.venv`.
- Run the following (replace the `-i` parameter with the Vim documentation
  location on your computer):
  ```
  scripts/h2h.py -i /usr/share/vim/vim92/doc/ -o html/
  ```
  The script offers a few options; run with `-h` to see what is available.

## License

This code is made freely available under the MIT License (see file LICENSE).
