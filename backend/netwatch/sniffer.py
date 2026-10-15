"""Passive capture on the watched interface.

Headers are parsed by hand with struct so byte counting keeps up with fast
downloads; only the rare interesting packets (ARP, DNS, mDNS, DHCP) are handed
to scapy for full dissection.
"""

import logging
import socket
import struct
import threading
import time
from collections import defaultdict, deque

from scapy.all import ARP, DHCP, DNS, Ether

from .alerts import Alerter
from .blocklist import Blocklist
from .config import FLUSH_INTERVAL_S, UPLOAD_ALERT_MB_PER_MIN
from .db import Database
from .devices import DeviceTracker
from .network import Interface

log = logging.getLogger(__name__)

ETH_P_ALL = 0x0003
PACKET_OUTGOING = 4

# Outbound ports with almost no legitimate home use, but common for backdoors,
# botnet C2 and remote shells.
SUSPICIOUS_PORTS = {
    23: "Telnet", 1337: "common backdoor", 2323: "Telnet (IoT botnets)", 4444: "Metasploit default",
    5555: "Android ADB", 6666: "IRC (botnet C2)", 6667: "IRC (botnet C2)", 31337: "common backdoor",
}
PORT_SCAN_WINDOW_S = 60
PORT_SCAN_THRESHOLD = 20  # distinct ports probed by one source inside the window
DNS_CACHE_MAX = 20000


class Sniffer:
    def __init__(self, iface: Interface, db: Database, tracker: DeviceTracker,
                 alerter: Alerter, blocklist: Blocklist):
        self.iface = iface
        self.db = db
        self.tracker = tracker
        self.alerter = alerter
        self.blocklist = blocklist

        self._our_mac = bytes.fromhex(iface.mac.replace(":", ""))
        self.total_up = 0
        self.total_down = 0
        self.started_at: float | None = None
        self.error: str | None = None

        self._lock = threading.Lock()
        self._buckets: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
        self._dests: dict[tuple[int, str], list] = {}
        self._dns: dict[str, str] = {}  # remote ip -> domain it was resolved from
        self._arp: dict[str, str] = {}  # ip -> mac last claimed via ARP
        self._syns: dict[str, deque] = defaultdict(deque)  # src ip -> (ts, dport)
        self._stop = threading.Event()
        self._threads = [
            threading.Thread(target=self._capture, name="sniffer", daemon=True),
            threading.Thread(target=self._flush_loop, name="sniffer-flush", daemon=True),
        ]

    def start(self) -> None:
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()

    # Capture -----------------------------------------------------------------

    def _capture(self) -> None:
        try:
            sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            sock.bind((self.iface.name, 0))
            sock.settimeout(1.0)
        except PermissionError:
            self.error = "Packet capture needs CAP_NET_RAW (run the container with --cap-add NET_RAW)."
            log.error(self.error)
            return
        except OSError as e:
            self.error = f"Packet capture unavailable on {self.iface.name}: {e}"
            log.error(self.error)
            return
        self.started_at = time.time()
        log.info("capturing on %s", self.iface.name)

        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                self._handle(data, addr[2] == PACKET_OUTGOING)
            except Exception:
                log.debug("failed to parse packet", exc_info=True)
        sock.close()

    def _handle(self, data: bytes, outgoing: bool) -> None:
        if len(data) < 14:
            return
        ethertype = struct.unpack_from("!H", data, 12)[0]
        offset = 14
        if ethertype == 0x8100 and len(data) >= 18:  # VLAN tag
            ethertype = struct.unpack_from("!H", data, 16)[0]
            offset = 18

        if ethertype == 0x0806:
            self._on_arp(Ether(data))
            return

        if ethertype == 0x0800 and len(data) >= offset + 20:
            ihl = (data[offset] & 0x0F) * 4
            proto = data[offset + 9]
            src = socket.inet_ntop(socket.AF_INET, data[offset + 12:offset + 16])
            dst = socket.inet_ntop(socket.AF_INET, data[offset + 16:offset + 20])
            l4 = offset + ihl
        elif ethertype == 0x86DD and len(data) >= offset + 40:
            proto = data[offset + 6]
            src = socket.inet_ntop(socket.AF_INET6, data[offset + 8:offset + 24])
            dst = socket.inet_ntop(socket.AF_INET6, data[offset + 24:offset + 40])
            l4 = offset + 40
        else:
            return

        sport = dport = 0
        if proto in (6, 17) and len(data) >= l4 + 4:
            sport, dport = struct.unpack_from("!HH", data, l4)

        to_us = data[0:6] == self._our_mac
        if outgoing:
            self._count(dst, len(data), up=True)
        elif to_us:
            self._count(src, len(data), up=False)

        if proto == 17 and (sport in (53, 5353, 67, 68) or dport in (5353, 67, 68)):
            self._on_udp_service(Ether(data), sport, dport)
        elif proto == 6 and len(data) >= l4 + 14:
            flags = data[l4 + 13]
            is_syn = flags & 0x02 and not flags & 0x10
            if is_syn and outgoing and dport in SUSPICIOUS_PORTS:
                self._on_suspicious_port(dst, dport)
            elif is_syn and to_us:
                self._on_inbound_syn(src, dport)

    def _count(self, remote: str, size: int, up: bool) -> None:
        minute = int(time.time() // 60)
        with self._lock:
            bucket = self._buckets[minute]
            bucket[0 if up else 1] += size
            bucket[2] += 1
            dest = self._dests.get((minute, remote))
            if dest is None:
                dest = self._dests[(minute, remote)] = [0, 0, self._dns.get(remote)]
            dest[0 if up else 1] += size
            if up:
                self.total_up += size
            else:
                self.total_down += size

    # Protocol handlers ---------------------------------------------------------

    def _on_arp(self, pkt) -> None:
        arp = pkt[ARP]
        mac, ip = arp.hwsrc.lower(), arp.psrc
        if ip == "0.0.0.0":
            return
        self.tracker.seen(mac, ip)

        previous = self._arp.get(ip)
        self._arp[ip] = mac
        if previous and previous != mac and ip == self.iface.gateway:
            self.alerter.fire(
                f"arp-gateway:{mac}", "arp_spoof", "critical",
                f"Router's MAC address changed ({ip})",
                f"{ip} moved from {previous} to {mac}. Unless you just replaced your router, "
                "another device may be impersonating it (ARP spoofing / man-in-the-middle).",
                mac=mac,
            )

    def _on_udp_service(self, pkt, sport: int, dport: int) -> None:
        mac = pkt[Ether].src.lower()

        if DHCP in pkt:
            for opt in pkt[DHCP].options:
                if isinstance(opt, tuple) and opt[0] == "hostname":
                    name = opt[1].decode(errors="ignore") if isinstance(opt[1], bytes) else str(opt[1])
                    self.tracker.seen(mac, None, name)
            return

        if DNS not in pkt:
            return
        dns = pkt[DNS]

        if sport == 53 and dns.qr == 1:
            qname = dns.qd[0].qname.decode(errors="ignore").rstrip(".") if dns.qd else None
            for rr in dns.an or []:
                if rr.type not in (1, 28):
                    continue
                with self._lock:
                    if len(self._dns) > DNS_CACHE_MAX:
                        self._dns.clear()
                    self._dns[str(rr.rdata)] = qname
            if qname:
                self._check_blocklist(qname)

        elif sport == 5353 or dport == 5353:
            # mDNS announcements: "<name>.local A <ip>" tells us a device's name.
            for rr in dns.an or []:
                if rr.type != 1:
                    continue
                name = rr.rrname.decode(errors="ignore").rstrip(".")
                if name.endswith(".local"):
                    self.tracker.seen(mac, str(rr.rdata), name.removesuffix(".local"))

    def _check_blocklist(self, domain: str) -> None:
        hit = self.blocklist.match(domain)
        if hit:
            self.alerter.fire(
                f"blocklist:{domain}", "blocklist", "serious",
                f"Lookup of a blocklisted domain: {domain}",
                f"This laptop resolved {domain}, which matches '{hit}' in your blocklists.",
            )

    def _on_suspicious_port(self, remote: str, port: int) -> None:
        self.alerter.fire(
            f"port:{remote}:{port}", "suspicious_port", "serious",
            f"Outbound connection on port {port} ({SUSPICIOUS_PORTS[port]})",
            f"This laptop opened a connection to {remote}:{port}"
            + (f" ({self._dns[remote]})" if remote in self._dns else "") + ".",
            cooldown_s=24 * 3600,
        )

    def _on_inbound_syn(self, src: str, dport: int) -> None:
        now = time.time()
        with self._lock:
            probes = self._syns[src]
            probes.append((now, dport))
            while probes and now - probes[0][0] > PORT_SCAN_WINDOW_S:
                probes.popleft()
            ports = {p for _, p in probes}
        if len(ports) >= PORT_SCAN_THRESHOLD:
            self.alerter.fire(
                f"portscan:{src}", "port_scan", "serious",
                f"Possible port scan from {src}",
                f"{src} tried {len(ports)} different ports on this laptop within a minute.",
            )

    # Persistence ---------------------------------------------------------------

    def _flush_loop(self) -> None:
        while not self._stop.wait(FLUSH_INTERVAL_S):
            try:
                self.flush()
            except Exception:
                log.exception("flush failed")

    def flush(self) -> None:
        with self._lock:
            buckets, self._buckets = self._buckets, defaultdict(lambda: [0, 0, 0])
            dests, self._dests = self._dests, {}
        if not buckets:
            return
        self.db.add_traffic(dict(buckets), dests)

        minute = int(time.time() // 60)
        uploaded = self.db.minute_upload(minute)
        if uploaded > UPLOAD_ALERT_MB_PER_MIN * 1_000_000:
            self.alerter.fire(
                "upload-burst", "upload_burst", "warning",
                f"Heavy upload: {uploaded / 1_000_000:.0f} MB in one minute",
                "Expected for backups, cloud sync or video calls; unexpected otherwise. "
                "Check the top destinations on the Traffic screen.",
                cooldown_s=30 * 60,
            )
