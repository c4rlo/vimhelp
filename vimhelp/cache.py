import datetime
import logging
import threading

_MAX_AGE = datetime.timedelta(minutes=3)


class Cache:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            timestamp, value = entry
            if datetime.datetime.utcnow() - timestamp > _MAX_AGE:
                logging.info("cache entry '%s' is expired", key)
                del self._cache[key]
                return None
            return value

    def put(self, key, value):
        with self._lock:
            logging.info("writing '%s' to inproc cache", key)
            self._cache[key] = datetime.datetime.utcnow(), value
