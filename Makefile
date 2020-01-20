deps:
	pip2 install -t lib -r requirements.txt -U --upgrade-strategy=eager

deploy: deps
	gcloud app deploy --no-promote

run:
	CLOUDSDK_PYTHON=python2 dev_appserver.py --support_datastore_emulator=1 --application=vimhelp2 app.yaml

clean:
	rm -rf lib __pycache__

.PHONY: deps deploy run clean
