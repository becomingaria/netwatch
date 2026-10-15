"""FastAPI app: REST API for the UI, a live WebSocket feed, and the built frontend."""

import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, network
from .alerts import Alerter
from .blocklist import Blocklist
from .db import Database
from .devices import DeviceTracker
from .scanner import Scanner
from .sniffer import Sniffer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("netwatch")

LIVE_TICK_S = 2
MAX_CHART_POINTS = 240


class State:
    iface: network.Interface
    db: Database
    alerter: Alerter
    blocklist: Blocklist
    tracker: DeviceTracker
    scanner: Scanner
    sniffer: Sniffer


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.iface = network.detect(config.IFACE)
    log.info("watching %s (%s, %s) on %s, gateway %s", state.iface.name, state.iface.ip,
             state.iface.mac, state.iface.network, state.iface.gateway)
    state.db = Database(config.DATA_DIR / "netwatch.db")
    state.db.prune(config.RETENTION_DAYS)
    state.alerter = Alerter(state.db)
    state.blocklist = Blocklist(config.DATA_DIR / "blocklists")
    state.tracker = DeviceTracker(state.db, state.alerter, state.iface.mac, state.iface.network_id)
    state.scanner = Scanner(state.iface, state.tracker, state.alerter, config.SCAN_INTERVAL_S)
    state.sniffer = Sniffer(state.iface, state.db, state.tracker, state.alerter, state.blocklist)
    state.sniffer.start()
    state.scanner.start()
    yield
    state.scanner.stop()
    state.sniffer.stop()
    state.sniffer.flush()


app = FastAPI(title="Netwatch", lifespan=lifespan)


def _device_view(d: dict) -> dict:
    now = time.time()
    return {
        **d,
        "trusted": bool(d["trusted"]),
        "is_self": d["mac"] == state.iface.mac,
        "is_gateway": d["ip"] is not None and d["ip"] == state.iface.gateway,
        "online": now - d["last_seen"] < config.OFFLINE_AFTER_S,
    }


@app.get("/api/status")
def status():
    return {
        "interface": state.iface.name,
        "ip": state.iface.ip,
        "mac": state.iface.mac,
        "network": str(state.iface.network),
        "gateway": state.iface.gateway,
        "capturing": state.sniffer.started_at is not None and state.sniffer.error is None,
        "capture_error": state.sniffer.error,
        "last_scan": state.scanner.last_scan,
        "scan_error": state.scanner.error,
        "blocklist_size": len(state.blocklist.domains),
    }


@app.get("/api/devices")
def devices():
    return [_device_view(d) for d in state.db.list_devices()]


class DeviceUpdate(BaseModel):
    label: str | None = None
    category: str | None = None
    trusted: bool | None = None
    notes: str | None = None


@app.patch("/api/devices/{mac}")
def update_device(mac: str, update: DeviceUpdate):
    device = state.db.update_device(mac.lower(), update.model_dump(exclude_unset=True))
    if device is None:
        raise HTTPException(404, "Unknown device")
    return _device_view(device)


@app.delete("/api/devices/{mac}")
def forget_device(mac: str):
    state.db.delete_device(mac.lower())
    return {"ok": True}


@app.post("/api/scan")
def scan_now():
    state.scanner.trigger()
    return {"ok": True}


@app.get("/api/traffic")
def traffic(minutes: int = 60):
    minutes = max(5, min(minutes, config.RETENTION_DAYS * 24 * 60))
    step = max(1, -(-minutes // MAX_CHART_POINTS))  # minutes per chart point
    now_minute = int(time.time() // 60)
    end = now_minute - now_minute % step + step  # exclusive, aligned to step
    since = end - step * -(-minutes // step)

    up, down = defaultdict(int), defaultdict(int)
    for r in state.db.traffic_series(since):
        bucket = r["minute"] - (r["minute"] - since) % step
        up[bucket] += r["up"]
        down[bucket] += r["down"]
    # Zero-filled so gaps read as "no traffic" rather than being interpolated over.
    series = [{"t": m * 60, "up": up[m], "down": down[m]} for m in range(since, end, step)]
    return {
        "step_s": step * 60,
        "series": series,
        "destinations": state.db.top_destinations(since),
        "total_up": sum(up.values()),
        "total_down": sum(down.values()),
    }


@app.get("/api/alerts")
def alerts():
    return state.db.list_alerts()


@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int):
    state.db.acknowledge_alert(alert_id)
    return {"ok": True}


@app.post("/api/alerts/ack-all")
def ack_all():
    state.db.acknowledge_alert(None)
    return {"ok": True}


@app.post("/api/blocklist/reload")
def reload_blocklist():
    state.blocklist.reload()
    return {"domains": len(state.blocklist.domains)}


@app.websocket("/ws/live")
async def live(ws: WebSocket):
    """Pushes current upload/download rates plus counters the UI uses to refetch lists."""
    await ws.accept()
    prev_up, prev_down, prev_t = state.sniffer.total_up, state.sniffer.total_down, time.monotonic()
    try:
        while True:
            await asyncio.sleep(LIVE_TICK_S)
            up, down, t = state.sniffer.total_up, state.sniffer.total_down, time.monotonic()
            elapsed = max(t - prev_t, 1e-6)
            await ws.send_json({
                "t": time.time(),
                "up_bps": (up - prev_up) / elapsed,
                "down_bps": (down - prev_down) / elapsed,
                "alerts": state.db.alert_summary(),
                "devices": state.db.device_count(),
            })
            prev_up, prev_down, prev_t = up, down, t
    except WebSocketDisconnect:
        pass


if config.STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (config.STATIC_DIR / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(config.STATIC_DIR.resolve()):
            return FileResponse(candidate)
        return FileResponse(config.STATIC_DIR / "index.html")


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    run()
