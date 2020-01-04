# vimhelp.org

This is the code behind the https://vimhelp.org website. It runs on
[Google App Engine](https://cloud.google.com/appengine/).

To deploy:

```sh
$ pip2 install -t lib -r requirements.txt
$ gcloud app deploy  # optionally add: --no-promote
```

This code is made freely available under the MIT License (see file LICENSE).
