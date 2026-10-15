"""Alert creation with per-key cooldowns so one noisy event doesn't flood the list."""

import logging
import threading
import time

from .db import Database

log = logging.getLogger(__name__)

SEVERITIES = ("info", "warning", "serious", "critical")


class Alerter:
    def __init__(self, db: Database):
        self._db = db
        self._last_fired: dict[str, float] = {}
        self._lock = threading.Lock()

    def fire(self, key: str, kind: str, severity: str, title: str,
             detail: str | None = None, mac: str | None = None, cooldown_s: float = 3600) -> None:
        assert severity in SEVERITIES
        now = time.time()
        with self._lock:
            if now - self._last_fired.get(key, 0) < cooldown_s:
                return
            self._last_fired[key] = now
        log.info("alert [%s] %s", severity, title)
        self._db.add_alert(kind, severity, title, detail, mac)
