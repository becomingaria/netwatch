"""Active discovery: periodic ARP sweep of the local subnet plus reverse-DNS names."""

import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

from scapy.all import ARP, Ether, srp

from .alerts import Alerter
from .devices import DeviceTracker
from .network import Interface

log = logging.getLogger(__name__)

RDNS_TIMEOUT_S = 4


def _reverse_dns(ip: str) -> str | None:
    try:
        name = socket.gethostbyaddr(ip)[0]
    except OSError:
        return None
    # systemd-resolved synthesizes "_gateway" for the default router; it isn't a real name.
    return None if name == ip or name.startswith("_gateway") else name


class Scanner:
    def __init__(self, iface: Interface, tracker: DeviceTracker, alerter: Alerter, interval_s: int):
        self.iface = iface
        self.tracker = tracker
        self.alerter = alerter
        self.interval_s = interval_s
        self.last_scan: float | None = None
        self.error: str | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._run, name="arp-scanner", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def trigger(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
                self.error = None
            except Exception as e:
                self.error = f"ARP sweep failed: {e}"
                log.exception("ARP sweep failed")
            self._wake.wait(self.interval_s)
            self._wake.clear()

    def scan_once(self) -> int:
        targets = self.iface.scan_targets()
        log.info("ARP sweep of %s (%d addresses) on %s", self.iface.network, len(targets), self.iface.name)
        answered, _ = srp(
            [Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip) for ip in targets],
            iface=self.iface.name, timeout=3, retry=1, verbose=False,
        )
        hosts = {rcv[ARP].hwsrc.lower(): rcv[ARP].psrc for _, rcv in answered}
        hosts[self.iface.mac] = self.iface.ip

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {mac: pool.submit(_reverse_dns, ip) for mac, ip in hosts.items()}
            wait(futures.values(), timeout=RDNS_TIMEOUT_S)
        for mac, ip in hosts.items():
            future = futures[mac]
            name = future.result() if future.done() else None
            self.tracker.seen(mac, ip, name)

        if not self.tracker.baseline_done:
            self.tracker.finish_baseline()
            self.alerter.fire(
                "baseline", "baseline", "info",
                f"Baseline recorded: {len(hosts)} devices on {self.iface.network}",
                "Devices that join from now on will raise a 'New device' alert.",
                cooldown_s=0,
            )
        self.last_scan = time.time()
        log.info("ARP sweep found %d hosts", len(hosts))
        return len(hosts)
