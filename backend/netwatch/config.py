"""Runtime settings, all overridable through NETWATCH_* environment variables."""

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"NETWATCH_{name}", default)


DATA_DIR = Path(_env("DATA", "/data"))
STATIC_DIR = Path(_env("STATIC", str(Path(__file__).resolve().parent.parent / "static")))
IFACE = _env("IFACE", "") or None
HOST = _env("HOST", "127.0.0.1")
PORT = int(_env("PORT", "8787"))

SCAN_INTERVAL_S = int(_env("SCAN_INTERVAL", "120"))
FLUSH_INTERVAL_S = 10
RETENTION_DAYS = int(_env("RETENTION_DAYS", "7"))

# Alert when this laptop uploads more than this many MB within one minute.
UPLOAD_ALERT_MB_PER_MIN = float(_env("UPLOAD_ALERT_MB", "200"))
# Devices unseen for this long are shown as offline.
OFFLINE_AFTER_S = int(_env("OFFLINE_AFTER", "600"))
