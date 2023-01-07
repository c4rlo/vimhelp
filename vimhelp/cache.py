import logging
import threading

import gevent

from .dbmodel import GlobalInfo, ndb_context


_REFRESH_INTERVAL_SEC = 120


class Cache:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, project, key):
        with self._lock:
            return self._cache.get(project, {}).get(key)

    def put(self, project, key, value):
        with self._lock:
            logging.info("writing %s:%s to inproc cache", project, key)
            self._cache.setdefault(project, {})[key] = value

    def clear(self, project):
        with self._lock:
            if c := self._cache.get(project):
                c.clear()

    def start_refresh_loop(self, warmup_callback):
        update_times = Cache._get_update_times()
        gevent.spawn_later(
            _REFRESH_INTERVAL_SEC, self._refresh, update_times, warmup_callback
        )

    def _refresh(self, old_update_times, warmup_callback):
        update_times = Cache._get_update_times()
        for project, update_time in update_times.items():
            old_update_time = old_update_times.get(project)
            if old_update_time is None or update_time > old_update_time:
                logging.info(
                    "project %s was updated (%s < %s), refreshing cache",
                    project,
                    old_update_time,
                    update_time,
                )
                self.clear(project)
                warmup_callback(project)
            else:
                logging.info(
                    "project %s was not updated, not refreshing cache", project
                )
        gevent.spawn_later(
            _REFRESH_INTERVAL_SEC, self._refresh, update_times, warmup_callback
        )

    @staticmethod
    def _get_update_times():
        with ndb_context():
            return {g.key.id(): g.last_update_time for g in GlobalInfo.query()}
