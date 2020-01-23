deps:
	pip2 install -t lib -U --upgrade-strategy=eager -r requirements.txt

deploy: deps
	gcloud app deploy --no-promote

run:
	CLOUDSDK_PYTHON=python2 dev_appserver.py --application=vimhelp2 app.yaml

clean:
	rm -rf lib __pycache__

.PHONY: deps deploy run clean
