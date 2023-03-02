# vimhelp.org

This is the code behind the https://vimhelp.org website. It runs on
[Google App Engine](https://cloud.google.com/appengine/).

## Running on Google App Engine

To make testing and deploying easier, a `tasks.py` file exists for use
with the [Invoke](https://www.pyinvoke.org/) tool.

## Generating static site

To generate a static site instead of running on Google App Engine, run the
following (replace the `-i` parameter with the Vim documentation location on
your computer):

    python3 -m venv --upgrade-deps .venv
    .venv/bin/pip install -r requirements.txt
    scripts/h2h.py -i /usr/share/vim/vim90/doc/ -o html/

## License

This code is made freely available under the MIT License (see file LICENSE).
