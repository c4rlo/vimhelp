set shell := ["bash", "-euo", "pipefail", "-c"]

project_staging := "vimhelp-staging"
project_prod := "vimhelp-hrd"
dev_env := '''
export PYTHONDEVMODE=1
export PYTHONWARNINGS='default,ignore:unclosed:ResourceWarning:sys,ignore:This process (pid=:DeprecationWarning:gevent.os'
export VIMHELP_ENV=dev
export FLASK_DEBUG=1
export GOOGLE_CLOUD_PROJECT=vimhelp-staging
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/private/gcloud-creds/vimhelp-staging-owner.json"
'''

# Run linters.
lint:
    uv sync --locked
    ruff check .
    ruff format --check
    ty check

# Run the app locally against staging.
[arg("gunicorn", long="gunicorn", value="1")]
[arg("tracemalloc", long="tracemalloc", value="1")]
run gunicorn="" tracemalloc="": ensure-private-mount
    #!/usr/bin/env bash
    set -euo pipefail

    if [[ "{{ gunicorn }}" == 1 ]]; then
        cmd=(gunicorn -c gunicorn.conf.dev.py)
    else
        cmd=(flask --app vimhelp.webapp --debug run)
    fi

    if [[ "{{ tracemalloc }}" == 1 ]]; then
        export PYTHONTRACEMALLOC=1
    fi

    {{ dev_env }}

    exec uv run "${cmd[@]}"

# Show Flask routes.
show-routes: ensure-private-mount
    #!/usr/bin/env bash
    set -euo pipefail

    {{ dev_env }}

    exec uv run flask --app vimhelp.webapp --debug routes

# Deploy the app, or cron.yaml with --cron.
[arg("target", pattern="^(staging|prod|all)$")]
[arg("cron", long="cron", value="1")]
deploy target="staging" cron="": lint ensure-private-mount
    #!/usr/bin/env bash
    set -euo pipefail

    uv export -q --locked --no-emit-project -o requirements.txt

    case "{{ target }}" in
        all)
            projects=({{ project_staging }} {{ project_prod }})
            ;;
        staging)
            projects=({{ project_staging }})
            ;;
        prod)
            projects=({{ project_prod }})
            ;;
    esac

    deploy_args=()
    if [[ "{{ cron }}" == 1 ]]; then
        deploy_args=(cron.yaml)
    fi

    for project in "${projects[@]}"; do
        gcloud app deploy --project="$project" --quiet "${deploy_args[@]}"

        mapfile -t old_vers < <(
            gcloud app versions list \
                --project="$project" \
                --format='value(id)' \
                --filter='traffic_split=0'
        )
        if ((${#old_vers[@]} > 0)); then
            printf 'Deleting old version(s): %s\n' "${old_vers[*]}"
            gcloud app versions delete --project="$project" --quiet "${old_vers[@]}"
        fi
    done

# Clean up build artefacts.
clean:
    rm -rf .ruff_cache .venv __pycache__ requirements.txt vimhelp/__pycache__ vimhelp.egg-info

# Interactive shell with virtualenv and datastore available.
sh: ensure-private-mount
    #!/usr/bin/env bash
    set -euo pipefail

    {{ dev_env }}

    . .venv/bin/activate
    "${SHELL:-bash}"
    echo "Exited vimhelp shell"

# Mount ~/private if it is not mounted.
[private]
ensure-private-mount:
    #!/usr/bin/env bash
    set -euo pipefail

    priv_dir="$HOME/private"
    if [[ "$(stat -c %d "$priv_dir")" == "$(stat -c %d "$(dirname "$priv_dir")")" ]]; then
        sudo systemctl start "$priv_dir"
    fi
