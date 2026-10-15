"""SQLite storage. One connection shared across threads, guarded by a lock."""

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    mac         TEXT PRIMARY KEY,
    ip          TEXT,
    hostname    TEXT,
    vendor      TEXT,
    label       TEXT,
    category    TEXT,
    trusted     INTEGER NOT NULL DEFAULT 0,
    notes       TEXT,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL
);

-- This laptop's own traffic, bucketed per minute (epoch minute).
CREATE TABLE IF NOT EXISTS traffic (
    minute   INTEGER PRIMARY KEY,
    up       INTEGER NOT NULL DEFAULT 0,
    down     INTEGER NOT NULL DEFAULT 0,
    packets  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS destinations (
    minute  INTEGER NOT NULL,
    remote  TEXT NOT NULL,
    domain  TEXT,
    up      INTEGER NOT NULL DEFAULT 0,
    down    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (minute, remote)
);

CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL NOT NULL,
    kind          TEXT NOT NULL,
    severity      TEXT NOT NULL,
    title         TEXT NOT NULL,
    detail        TEXT,
    mac           TEXT,
    acknowledged  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts);

-- Networks whose existing devices have been recorded as a baseline. A laptop
-- moves between networks, so "new device" only means new to *that* network.
CREATE TABLE IF NOT EXISTS networks (
    id          TEXT PRIMARY KEY,
    first_seen  REAL NOT NULL
);
"""

EDITABLE_DEVICE_FIELDS = ("label", "category", "trusted", "notes")


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def _query(self, sql: str, params=()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _exec(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    # Devices -----------------------------------------------------------------

    def device_count(self) -> int:
        return self._query("SELECT COUNT(*) AS n FROM devices")[0]["n"]

    def upsert_device(self, mac: str, ip: str | None, vendor: str | None,
                      hostname: str | None = None, seen: float | None = None) -> bool:
        """Record a sighting. Returns True if the device was never seen before."""
        seen = seen or time.time()
        with self._lock:
            row = self._conn.execute("SELECT mac FROM devices WHERE mac = ?", (mac,)).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO devices (mac, ip, hostname, vendor, first_seen, last_seen)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (mac, ip, hostname, vendor, seen, seen),
                )
                return True
            self._conn.execute(
                "UPDATE devices SET ip = COALESCE(?, ip), hostname = COALESCE(?, hostname),"
                " vendor = COALESCE(vendor, ?), last_seen = MAX(last_seen, ?) WHERE mac = ?",
                (ip, hostname, vendor, seen, mac),
            )
            return False

    def list_devices(self) -> list[dict]:
        return self._query("SELECT * FROM devices ORDER BY last_seen DESC")

    def get_device(self, mac: str) -> dict | None:
        rows = self._query("SELECT * FROM devices WHERE mac = ?", (mac,))
        return rows[0] if rows else None

    def update_device(self, mac: str, fields: dict) -> dict | None:
        fields = {k: v for k, v in fields.items() if k in EDITABLE_DEVICE_FIELDS}
        if fields:
            assignments = ", ".join(f"{k} = ?" for k in fields)
            self._exec(f"UPDATE devices SET {assignments} WHERE mac = ?", (*fields.values(), mac))
        return self.get_device(mac)

    def delete_device(self, mac: str) -> None:
        self._exec("DELETE FROM devices WHERE mac = ?", (mac,))

    def network_known(self, network_id: str) -> bool:
        return bool(self._query("SELECT 1 FROM networks WHERE id = ?", (network_id,)))

    def mark_network_known(self, network_id: str) -> None:
        self._exec("INSERT OR IGNORE INTO networks (id, first_seen) VALUES (?, ?)", (network_id, time.time()))

    # Traffic -----------------------------------------------------------------

    def add_traffic(self, buckets: dict[int, list[int]],
                    destinations: dict[tuple[int, str], list]) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            self._conn.executemany(
                "INSERT INTO traffic (minute, up, down, packets) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(minute) DO UPDATE SET up = up + excluded.up,"
                " down = down + excluded.down, packets = packets + excluded.packets",
                [(m, up, down, pk) for m, (up, down, pk) in buckets.items()],
            )
            self._conn.executemany(
                "INSERT INTO destinations (minute, remote, domain, up, down) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(minute, remote) DO UPDATE SET up = up + excluded.up,"
                " down = down + excluded.down, domain = COALESCE(excluded.domain, domain)",
                [(m, remote, domain, up, down) for (m, remote), (up, down, domain) in destinations.items()],
            )
            self._conn.execute("COMMIT")

    def traffic_series(self, since_minute: int) -> list[dict]:
        return self._query(
            "SELECT minute, up, down, packets FROM traffic WHERE minute >= ? ORDER BY minute",
            (since_minute,),
        )

    def minute_upload(self, minute: int) -> int:
        rows = self._query("SELECT up FROM traffic WHERE minute = ?", (minute,))
        return rows[0]["up"] if rows else 0

    def top_destinations(self, since_minute: int, limit: int = 15) -> list[dict]:
        return self._query(
            "SELECT remote, MAX(domain) AS domain, SUM(up) AS up, SUM(down) AS down,"
            " SUM(up + down) AS total, MAX(minute) AS last_minute"
            " FROM destinations WHERE minute >= ? GROUP BY remote ORDER BY total DESC LIMIT ?",
            (since_minute, limit),
        )

    def known_domain(self, domain: str) -> bool:
        return bool(self._query("SELECT 1 FROM destinations WHERE domain = ? LIMIT 1", (domain,)))

    # Alerts ------------------------------------------------------------------

    def add_alert(self, kind: str, severity: str, title: str,
                  detail: str | None = None, mac: str | None = None) -> int:
        cur = self._exec(
            "INSERT INTO alerts (ts, kind, severity, title, detail, mac) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), kind, severity, title, detail, mac),
        )
        return cur.lastrowid

    def list_alerts(self, limit: int = 200) -> list[dict]:
        return self._query("SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,))

    def acknowledge_alert(self, alert_id: int | None) -> None:
        if alert_id is None:
            self._exec("UPDATE alerts SET acknowledged = 1")
        else:
            self._exec("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))

    def alert_summary(self) -> dict:
        row = self._query(
            "SELECT COALESCE(MAX(id), 0) AS latest_id,"
            " SUM(CASE WHEN acknowledged = 0 THEN 1 ELSE 0 END) AS unread FROM alerts"
        )[0]
        return {"latest_id": row["latest_id"], "unread": row["unread"] or 0}

    # Housekeeping ------------------------------------------------------------

    def prune(self, retention_days: int) -> None:
        cutoff_minute = int(time.time() // 60) - retention_days * 24 * 60
        self._exec("DELETE FROM traffic WHERE minute < ?", (cutoff_minute,))
        self._exec("DELETE FROM destinations WHERE minute < ?", (cutoff_minute,))
        self._exec("DELETE FROM alerts WHERE ts < ? AND acknowledged = 1", (cutoff_minute * 60,))
