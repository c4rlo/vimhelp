.PHONY: help venv lint run stage deploy clean

help:
	@echo "Makefile targets:"; \
	echo "  venv   - Create virtualenv with required dependencies"; \
	echo "  lint   - Run flake8 on sources"; \
	echo "  run    - Run app locally (assumes vimhelp-staging creds exist"; \
	echo "           in the expected filesystem location)"; \
	echo "  stage  - Deploy to staging env (vimhelp-staging.appspot.com)"; \
	echo "  deploy - Deploy to prod env (vimhelp.org)"; \
	echo "  clean  - Delete build artefacts"

venv:
	python3 -m venv --upgrade-deps .venv && \
	. .venv/bin/activate && \
	    pip install -U --upgrade-strategy=eager -r requirements.txt
	@echo; \
	echo "Now run: "; \
	echo "- '. .venv/bin/activate' to activate the virtualenv"; \
	echo "- 'deactivate' to leave it again"

lint:
	python3 -m flake8 --max-line-length=80 --exclude=.venv/,vimhelp/vimh2h.py \
	    --per-file-ignores='vimhelp/vimh2h.py:E221,E221,E272,E501,E701'

run:
	@[ -n "$$VIRTUAL_ENV" ] || { echo "Not in virtual env!"; exit 1; } || true
	GOOGLE_APPLICATION_CREDENTIALS=~/private/gcloud-creds/vimhelp-staging-owner.json \
	    GOOGLE_CLOUD_PROJECT=vimhelp-staging VIMHELP_ENV=dev \
	    gunicorn -k gevent --reload 'vimhelp.webapp:create_app()'

stage: lint
	yes | gcloud app deploy --project=vimhelp-staging

deploy: lint
	gcloud app deploy --project=vimhelp-hrd

clean:
	@[ -n "$$VIRTUAL_ENV" ] && { echo "In virtual env!"; exit 1; } || true
	rm -rf .venv vimhelp/__pycache__
