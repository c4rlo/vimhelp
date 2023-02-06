# Use with https://www.pyinvoke.org/

from invoke import task

import os
import pathlib
import shutil
import sys


VENV_DIR = pathlib.Path(".venv")
REQ_TXT = pathlib.Path("requirements.txt")

PRIV_DIR = pathlib.Path("~/private").expanduser()
STAGING_CREDENTIALS = PRIV_DIR / "gcloud-creds/vimhelp-staging-owner.json"

DEV_ENV = {
    "PYTHONDEVMODE": "1",
    # "PYTHONTRACEMALLOC": "1",
    "PYTHONWARNINGS": (
        "default,"
        "ignore:unclosed:ResourceWarning:werkzeug.serving,"
        "ignore:unclosed:ResourceWarning:flask.cli,"
        "ignore:setDaemon:DeprecationWarning:gunicorn.reloader"
    ),
    "VIMHELP_ENV": "dev",
    "GOOGLE_CLOUD_PROJECT": "vimhelp-staging",
    "GOOGLE_APPLICATION_CREDENTIALS": str(STAGING_CREDENTIALS),
}


os.chdir(pathlib.Path(__file__).parent)


@task
def venv(c):
    """Populate virtualenv."""
    if not os.path.exists(VENV_DIR):
        c.run(f"python -m venv --upgrade-deps {VENV_DIR}")
        c.run(f"{VENV_DIR}/bin/pip install -U wheel")
        print("Initialised venv.")
    c.run(f"{VENV_DIR}/bin/pip install -U --upgrade-strategy eager -r {REQ_TXT}")
    print("Updated venv.")


@task
def lint(c):
    """Run linters (flake8, black)."""
    c.run("flake8")
    c.run("black --check .")


@task(help={"gunicorn": "Run using gunicorn instead of 'flask run'"})
def run(c, gunicorn=False):
    """Run app locally against vimhelp-staging database."""
    _ensure_private_mount(c)
    if gunicorn:
        cmd = (
            f"{VENV_DIR}/bin/gunicorn -k gevent --reload "
            "'vimhelp.webapp:create_app()'"
        )
    else:
        cmd = f"{VENV_DIR}/bin/flask --app vimhelp.webapp --debug run"
    c.run(cmd, env=DEV_ENV)


@task
def show_routes(c):
    """Show Flask routes."""
    c.run(f"{VENV_DIR}/bin/flask --app vimhelp.webapp routes", env=DEV_ENV)


# fmt: off
@task(pre=[lint],
      help={
          "target":
          "Target environment: 'staging' (default), 'prod', 'all' (= staging + prod)"
      })
# fmt: on
def deploy(c, target="stage"):
    """Deploy app."""
    _ensure_private_mount(c)
    if target == "all":
        targets = "stage", "prod"
    else:
        targets = (target,)
    for t in targets:
        if t == "stage":
            cmd = "gcloud app deploy --quiet --project=vimhelp-staging"
        elif t == "prod":
            cmd = "gcloud app deploy --project=vimhelp-hrd"
        else:
            sys.exit(f"Invalid target name: '{t}'")
        c.run(cmd, pty=True)


@task
def clean(c):
    """Clean up build artefacts (virtualenv, __pycache__)."""
    for d in VENV_DIR, pathlib.Path("vimhelp/__pycache__"):
        if d.exists():
            shutil.rmtree(d)


def _ensure_private_mount(c):
    if PRIV_DIR.stat().st_dev == PRIV_DIR.parent.stat().st_dev:
        c.run(f"sudo systemctl start {PRIV_DIR}", pty=True)
