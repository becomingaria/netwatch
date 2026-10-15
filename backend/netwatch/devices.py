"""Turns sightings (from the ARP sweep or passively sniffed packets) into device records."""

import threading
import time

from . import vendor
from .alerts import Alerter
from .db import Database

# Passive sightings without new information are written at most this often per device.
SIGHTING_THROTTLE_S = 30


class DeviceTracker:
    def __init__(self, db: Database, alerter: Alerter, self_mac: str, network_id: str):
        self._db = db
        self._alerter = alerter
        self._self_mac = self_mac
        self._network_id = network_id
        self._last_write: dict[str, float] = {}
        self._lock = threading.Lock()
        # Until the first sweep of this network finishes, everything is "already here", not "new".
        self.baseline_done = db.network_known(network_id)

    def finish_baseline(self) -> None:
        self._db.mark_network_known(self._network_id)
        self.baseline_done = True

    def seen(self, mac: str, ip: str | None, hostname: str | None = None) -> None:
        mac = mac.lower()
        if mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00") or int(mac[:2], 16) & 0x01:
            return  # broadcast / multicast, not a device
        now = time.time()
        with self._lock:
            if hostname is None and now - self._last_write.get(mac, 0) < SIGHTING_THROTTLE_S:
                return
            self._last_write[mac] = now

        is_new = self._db.upsert_device(mac, ip, vendor.lookup(mac), hostname, now)
        if is_new and self.baseline_done and mac != self._self_mac:
            maker = vendor.lookup(mac) or ("randomized MAC" if vendor.is_randomized(mac) else "unknown maker")
            name = hostname or ip or mac
            self._alerter.fire(
                f"new-device:{mac}", "new_device", "warning",
                f"New device joined: {name}",
                f"{mac} ({maker}) appeared at {ip or 'unknown IP'}. Label it or mark it trusted if you recognise it.",
                mac=mac, cooldown_s=0,
            )
