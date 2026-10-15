"""Figure out which interface to watch and what subnet it sits on."""

import ipaddress
import socket
import struct
from dataclasses import dataclass

from scapy.all import get_if_addr, get_if_hwaddr

# Never ARP-sweep more than this many hosts, even on a big corporate subnet.
MAX_SCAN_PREFIX = 22


@dataclass(frozen=True)
class Interface:
    name: str
    ip: str
    mac: str
    network: ipaddress.IPv4Network
    gateway: str | None

    @property
    def network_id(self) -> str:
        return f"{self.network}|{self.gateway}"

    def scan_targets(self) -> list[str]:
        targets = [str(ip) for ip in self.network.hosts()]
        # On big subnets the gateway can fall outside the slice we sweep.
        if self.gateway and ipaddress.IPv4Address(self.gateway) not in self.network:
            targets.append(self.gateway)
        return targets


def _hex_ip(value: str) -> str:
    return socket.inet_ntoa(struct.pack("<I", int(value, 16)))


def _read_routes() -> list[dict]:
    with open("/proc/net/route") as f:
        lines = f.read().splitlines()[1:]
    routes = []
    for line in lines:
        cols = line.split()
        if len(cols) < 8:
            continue
        routes.append({
            "iface": cols[0],
            "dest": _hex_ip(cols[1]),
            "gateway": _hex_ip(cols[2]),
            "metric": int(cols[6]),
            "mask": _hex_ip(cols[7]),
        })
    return routes


def detect(preferred: str | None = None) -> Interface:
    routes = _read_routes()
    defaults = sorted((r for r in routes if r["dest"] == "0.0.0.0"), key=lambda r: r["metric"])

    if preferred:
        name = preferred
    elif defaults:
        name = defaults[0]["iface"]
    else:
        raise RuntimeError("No default route found; set NETWATCH_IFACE to the interface to watch")

    ip = get_if_addr(name)
    if ip == "0.0.0.0":
        raise RuntimeError(f"Interface {name} has no IPv4 address")
    mac = get_if_hwaddr(name).lower()
    gateway = next((r["gateway"] for r in defaults if r["iface"] == name), None)

    network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
    for r in routes:
        if r["iface"] != name or r["dest"] == "0.0.0.0" or r["gateway"] != "0.0.0.0":
            continue
        candidate = ipaddress.IPv4Network(f"{r['dest']}/{r['mask']}", strict=False)
        if ipaddress.IPv4Address(ip) in candidate:
            network = candidate
            break
    if network.prefixlen < MAX_SCAN_PREFIX:
        network = ipaddress.IPv4Network(f"{ip}/{MAX_SCAN_PREFIX}", strict=False)

    return Interface(name=name, ip=ip, mac=mac, network=network, gateway=gateway)
