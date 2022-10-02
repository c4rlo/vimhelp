import json as json_module
import logging

import geventhttpclient
import geventhttpclient.client
import gevent.ssl


class HttpClient:
    def __init__(self, concurrency):
        self._pool = geventhttpclient.client.HTTPClientPool(
            ssl_context_factory=gevent.ssl.create_default_context,
            concurrency=concurrency,
        )

    def get(self, url, headers):
        try:
            url = geventhttpclient.URL(url)
            client = self._pool.get_client(url)
            response = client.get(url.request_uri, headers=headers)
        except Exception as e:
            logging.error(e)
            raise HttpError(e, url)
        return HttpResponse(response, url)

    def post(self, url, json, headers):
        try:
            url = geventhttpclient.URL(url)
            client = self._pool.get_client(url)
            response = client.post(
                url.request_uri, body=json_module.dumps(json), headers=headers
            )
        except Exception as e:
            logging.error(e)
            raise HttpError(e, url)
        return HttpResponse(response, url)

    def close(self):
        self._pool.close()


class HttpResponse:
    def __init__(self, response, url):
        self.url = url
        self.body = bytes(response.read())
        response.release()
        self._response = response

    @property
    def status_code(self):
        return self._response.status_code

    def header(self, name):
        return self._response.get(name)


class HttpError(RuntimeError):
    def __init__(self, e, url):
        self._e = e
        self._url = url

    def __str__(self):
        return f"Failed HTTP request for {self._url}: {self._e}"
