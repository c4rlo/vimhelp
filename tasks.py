# Use with https://www.pyinvoke.org/

from invoke import task  # ty:ignore[unresolved-import]

import os
import pathlib
import sys


os.chdir(pathlib.Path(__file__).parent)


PRIV_DIR = pathlib.Path("~/private").expanduser()
STAGING_CREDENTIALS = PRIV_DIR / "gcloud-creds/vimhelp-staging-owner.json"

PROJECT_STAGING = "vimhelp-staging"
PROJECT_PROD = "vimhelp-hrd"

DEV_ENV = {
    "PYTHONDEVMODE": "1",
    "PYTHONWARNINGS": (
        "default,"
        "ignore:unclosed:ResourceWarning:sys,"
        "ignore:Type google._upb._message:DeprecationWarning:importlib._bootstrap,"
        "ignore:This process (pid=:DeprecationWarning:gevent.os"
    ),
    "VIMHELP_ENV": "dev",
    "FLASK_DEBUG": "1",
    "GOOGLE_CLOUD_PROJECT": PROJECT_STAGING,
    "GOOGLE_APPLICATION_CREDENTIALS": str(STAGING_CREDENTIALS),
}


@task
def lint(c):
    """Run linters."""
    c.run("uv sync --locked")
    c.run("ruff check .", pty=True)
    c.run("ruff format --check", pty=True)
    c.run("ty check", pty=True)


@task(
    help={
        "gunicorn": "Run using gunicorn instead of 'flask run'",
        "tracemalloc": "Run with tracemalloc enabled",
    },
)
def run(c, gunicorn=False, tracemalloc=False):
    """Run app locally against staging database."""
    _ensure_private_mount(c)
    if gunicorn:
        cmd = "uv run gunicorn -c gunicorn.conf.dev.py"
    else:
        cmd = "uv run flask --app vimhelp.webapp --debug run"
    if tracemalloc:
        env = DEV_ENV | {"PYTHONTRACEMALLOC": "1"}
    else:
        env = DEV_ENV
    c.run(cmd, env=env, pty=True)


@task
def show_routes(c):
    """Show Flask routes."""
    _ensure_private_mount(c)
    c.run("uv run flask --app vimhelp.webapp --debug routes", env=DEV_ENV, pty=True)


@task(
    pre=[lint],
    help={
        "target": "Target environment: 'staging' (default), 'prod', "
                  "'all' (= staging + prod)",
        "cron":   "Deploy cron.yaml instead of main app"
    },
)  # fmt: skip
def deploy(c, target="staging", cron=False):
    """Deploy app."""
    c.run("uv export -q --locked --no-emit-project -o requirements.txt")
    _ensure_private_mount(c)
    if target == "all":
        targets = "staging", "prod"
    else:
        targets = (target,)
    for t in targets:
        if t == "staging":
            cmd = f"gcloud app deploy --quiet --project={PROJECT_STAGING}"
        elif t == "prod":
            cmd = f"gcloud app deploy --project={PROJECT_PROD}"
        else:
            sys.exit(f"Invalid target name: '{t}'")
        if cron:
            cmd += " cron.yaml"
        c.run(cmd, pty=True)


@task
def clean(c):
    """Clean up build artefacts."""
    to_remove = (
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "requirements.txt",
        "vimhelp/__pycache__",
        "vimhelp.egg-info",
    )
    for d in to_remove:
        if pathlib.Path(d).exists():
            c.run(f"rm -rf {d}")


@task()
def sh(c):
    """Interactive shell with virtualenv and datastore available."""
    _ensure_private_mount(c)
    with c.prefix(". .venv/bin/activate"):
        c.run(os.getenv("SHELL", "bash"), env=DEV_ENV, pty=True)
    print("Exited vimhelp shell")


def _ensure_private_mount(c):
    if PRIV_DIR.stat().st_dev == PRIV_DIR.parent.stat().st_dev:
        c.run(f"sudo systemctl start {PRIV_DIR}", pty=True)
