"""Feeds hand-built packets through the sniffer and checks what it records."""

import ipaddress

import pytest
from scapy.all import ARP, BOOTP, DHCP, DNS, DNSQR, DNSRR, IP, TCP, UDP, Ether

from netwatch.alerts import Alerter
from netwatch.blocklist import Blocklist
from netwatch.db import Database
from netwatch.devices import DeviceTracker
from netwatch.network import Interface
from netwatch.sniffer import Sniffer

ME = "7c:d1:c3:dc:e9:33"
ROUTER = "00:11:22:33:44:55"
PHONE = "3c:22:fb:00:00:01"
IFACE = Interface("wlan0", "10.0.0.8", ME, ipaddress.IPv4Network("10.0.0.0/24"), "10.0.0.1")


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "t.db")
    alerter = Alerter(db)
    blocklist_dir = tmp_path / "blocklists"
    blocklist_dir.mkdir()
    (blocklist_dir / "bad.txt").write_text("0.0.0.0 evil.example\n# comment\n")
    tracker = DeviceTracker(db, alerter, ME, IFACE.network_id)
    tracker.finish_baseline()
    sniffer = Sniffer(IFACE, db, tracker, alerter, Blocklist(blocklist_dir))
    return db, sniffer


def feed(sniffer, pkt, outgoing=False):
    sniffer._handle(bytes(pkt), outgoing)


def kinds(db):
    return [a["kind"] for a in db.list_alerts()]


def test_counts_up_and_down_with_dns_names(env):
    db, s = env
    answer = Ether(src=ROUTER, dst=ME) / IP(src="10.0.0.1", dst="10.0.0.8") / UDP(sport=53, dport=40000) / DNS(
        qr=1, qd=DNSQR(qname="example.com"), an=[DNSRR(rrname="example.com", type="A", rdata="93.184.216.34")])
    feed(s, answer)
    up = Ether(src=ME, dst=ROUTER) / IP(src="10.0.0.8", dst="93.184.216.34") / TCP(dport=443, flags="A") / (b"x" * 500)
    down = Ether(src=ROUTER, dst=ME) / IP(src="93.184.216.34", dst="10.0.0.8") / TCP(sport=443, flags="A") / (b"x" * 1400)
    feed(s, up, outgoing=True)
    feed(s, down)
    s.flush()

    assert s.total_up == len(up)
    assert s.total_down == len(down) + len(answer)
    dest = next(d for d in db.top_destinations(0) if d["remote"] == "93.184.216.34")
    assert dest["domain"] == "example.com"
    assert (dest["up"], dest["down"]) == (len(up), len(down))


def test_new_device_and_dhcp_hostname(env):
    db, s = env
    feed(s, Ether(src=PHONE, dst="ff:ff:ff:ff:ff:ff") / IP(src="0.0.0.0", dst="255.255.255.255")
         / UDP(sport=68, dport=67) / BOOTP() / DHCP(options=[("message-type", "request"), ("hostname", b"pixel-7"), "end"]))
    device = db.get_device(PHONE)
    assert device["hostname"] == "pixel-7"
    assert "new_device" in kinds(db)


def test_mdns_name(env):
    db, s = env
    feed(s, Ether(src=PHONE, dst="01:00:5e:00:00:fb") / IP(src="10.0.0.50", dst="224.0.0.251") / UDP(sport=5353, dport=5353)
         / DNS(qr=1, aa=1, an=[DNSRR(rrname="Living-Room-TV.local", type="A", rdata="10.0.0.50")]))
    device = db.get_device(PHONE)
    assert (device["hostname"], device["ip"]) == ("Living-Room-TV", "10.0.0.50")


def test_gateway_arp_change_is_critical(env):
    db, s = env
    feed(s, Ether(src=ROUTER, dst=ME) / ARP(op=2, hwsrc=ROUTER, psrc="10.0.0.1", pdst="10.0.0.8"))
    feed(s, Ether(src=PHONE, dst=ME) / ARP(op=2, hwsrc=PHONE, psrc="10.0.0.1", pdst="10.0.0.8"))
    spoof = [a for a in db.list_alerts() if a["kind"] == "arp_spoof"]
    assert spoof and spoof[0]["severity"] == "critical"


def test_blocklisted_lookup(env):
    db, s = env
    feed(s, Ether(src=ROUTER, dst=ME) / IP(src="10.0.0.1", dst="10.0.0.8") / UDP(sport=53, dport=40000)
         / DNS(qr=1, qd=DNSQR(qname="cdn.evil.example"), an=[DNSRR(rrname="cdn.evil.example", rdata="6.6.6.6")]))
    assert "blocklist" in kinds(db)


def test_suspicious_outbound_port(env):
    db, s = env
    feed(s, Ether(src=ME, dst=ROUTER) / IP(src="10.0.0.8", dst="203.0.113.9") / TCP(dport=4444, flags="S"), outgoing=True)
    assert "suspicious_port" in kinds(db)


def test_port_scan(env):
    db, s = env
    for port in range(1000, 1025):
        feed(s, Ether(src=PHONE, dst=ME) / IP(src="10.0.0.50", dst="10.0.0.8") / TCP(dport=port, flags="S"))
    assert "port_scan" in kinds(db)


def test_ordinary_traffic_raises_nothing(env):
    db, s = env
    for port in (443, 443, 80):
        feed(s, Ether(src=ME, dst=ROUTER) / IP(src="10.0.0.8", dst="1.1.1.1") / TCP(dport=port, flags="S"), outgoing=True)
    assert kinds(db) == []


def test_baseline_is_per_network(tmp_path):
    db = Database(tmp_path / "t.db")
    home = DeviceTracker(db, Alerter(db), ME, "10.0.0.0/24|10.0.0.1")
    home.finish_baseline()
    cafe = DeviceTracker(db, Alerter(db), ME, "172.20.40.0/22|172.20.0.1")
    assert not cafe.baseline_done
    assert DeviceTracker(db, Alerter(db), ME, "10.0.0.0/24|10.0.0.1").baseline_done


def test_scan_targets_include_out_of_range_gateway():
    iface = Interface("wlan0", "172.20.42.120", ME, ipaddress.IPv4Network("172.20.40.0/22"), "172.20.0.1")
    targets = iface.scan_targets()
    assert "172.20.0.1" in targets and "172.20.42.1" in targets and len(targets) == 1023
