# Netwatch

A home network monitor that runs on this laptop. It does three things:

- **Devices**: finds everything on your LAN (ARP sweep, plus passively reading DHCP and mDNS),
  looks up the maker from the MAC address, and lets you label, categorise and mark devices as trusted.
- **Traffic**: this laptop's upload and download over time, live rates, and the top destinations
  (with domain names learned from DNS).
- **Alerts**:
  - a new device joins
  - the router's MAC address changes (ARP spoofing / man-in-the-middle)
  - a port scan against this laptop
  - outbound connections on backdoor or botnet ports
  - DNS lookups of blocklisted domains
  - unusually heavy upload

## What it can and can't see

On Wi-Fi, a laptop only sees **its own** traffic plus broadcast and multicast traffic from other devices.
That's enough to discover and name devices, but not to measure their bandwidth. To monitor every
device's traffic, run the backend on a machine connected to a switch mirror port, or on the router.
It's the same container; set `NETWATCH_IFACE` to the interface that receives the mirrored traffic.

## Run it

```sh
# One time only: let your user talk to Docker (then log out and back in)
sudo usermod -aG docker $USER

./netwatch.sh build             # builds the UI and the backend into one image
./netwatch.sh open              # starts the container and opens the app window
./netwatch.sh install-desktop   # adds "Netwatch" to your app menu
```

Other commands: `start`, `stop`, `restart`, `rebuild`, `logs`, `status`.

The container uses host networking with only the `NET_RAW` and `NET_ADMIN` capabilities, and the
API listens on `127.0.0.1:8787` only. Data lives in the `netwatch-data` Docker volume.

### Settings (environment variables for `./netwatch.sh start`)

| Variable | Default | Meaning |
|---|---|---|
| `NETWATCH_IFACE` | default-route interface | Interface to watch |
| `NETWATCH_PORT` | `8787` | UI/API port |
| `NETWATCH_SCAN_INTERVAL` | `120` | Seconds between ARP sweeps |
| `NETWATCH_UPLOAD_ALERT_MB` | `200` | Upload per minute that triggers an alert |
| `NETWATCH_RETENTION_DAYS` | `7` | How long traffic history is kept |

To pass a variable other than `NETWATCH_IFACE`/`NETWATCH_PORT`, add `-e` to the `docker run` line in `netwatch.sh`.

### Blocklists

Put domain lists (plain or hosts-file format) into the data volume's `blocklists/` folder, then reload:

```sh
docker exec netwatch sh -c 'python -c "import urllib.request as u; u.urlretrieve(\"https://urlhaus.abuse.ch/downloads/hostfile/\", \"/data/blocklists/urlhaus.txt\")"'
curl -X POST http://127.0.0.1:8787/api/blocklist/reload
```

## Develop

```sh
# Backend tests (needs Python 3.11+)
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest tests

# UI with hot reload against the running container
cd frontend && npm install && npm run dev    # http://localhost:5173
```

```
backend/netwatch/
  main.py       FastAPI app: REST API, /ws/live feed, serves the built UI
  sniffer.py    raw-socket capture, byte counting, DNS/mDNS/DHCP/ARP parsing, detections
  scanner.py    periodic ARP sweep + reverse DNS
  devices.py    sightings -> device records, "new device" alerts
  db.py         SQLite schema and queries
frontend/src/
  App.tsx       shell, navigation, live feed
  components/   Devices, Traffic (chart), Alerts
```
