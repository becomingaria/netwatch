import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, type Alert, type Device, type Status } from "./api";
import { AlertsView } from "./components/AlertsView";
import { DevicesView } from "./components/DevicesView";
import { TrafficView } from "./components/TrafficView";
import { formatRate } from "./format";
import { useLive } from "./useLive";

type Tab = "devices" | "traffic" | "alerts";
const TABS: Tab[] = ["devices", "traffic", "alerts"];
const DEVICE_REFRESH_MS = 30_000;

function savedTab(): Tab {
  try {
    const t = localStorage.getItem("netwatch.tab") as Tab | null;
    return t && TABS.includes(t) ? t : "devices";
  } catch {
    return "devices";
  }
}

export default function App() {
  const [tab, setTabState] = useState<Tab>(savedTab);
  const [status, setStatus] = useState<Status | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const { live, connected } = useLive();

  const setTab = (t: Tab) => {
    setTabState(t);
    try { localStorage.setItem("netwatch.tab", t); } catch { /* storage unavailable */ }
  };

  const loadDevices = useCallback(() => {
    api.devices().then(setDevices).catch(() => {});
    api.status().then(setStatus).catch(() => {});
  }, []);
  const loadAlerts = useCallback(() => { api.alerts().then(setAlerts).catch(() => {}); }, []);

  useEffect(() => {
    loadDevices();
    const id = window.setInterval(loadDevices, DEVICE_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [loadDevices]);

  // The live feed carries counters; refetch the full lists only when they move.
  useEffect(loadDevices, [live?.devices, loadDevices]);
  useEffect(loadAlerts, [live?.alerts.latest_id, loadAlerts]);

  const unread = live?.alerts.unread ?? alerts.filter((a) => !a.acknowledged).length;
  const problem = status?.capture_error ?? status?.scan_error;

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Sections">
        <div className="brand"><img src="/icon.svg" alt="" />Netwatch</div>
        <NavItem label="Devices" active={tab === "devices"} onClick={() => setTab("devices")}
          extra={<span className="nav-count">{devices.length}</span>} />
        <NavItem label="Traffic" active={tab === "traffic"} onClick={() => setTab("traffic")} />
        <NavItem label="Alerts" active={tab === "alerts"} onClick={() => setTab("alerts")}
          extra={unread > 0 ? <span className="nav-badge" aria-label={`${unread} unread`}>{unread}</span> : null} />

        <div className="sidebar-foot">
          <div className="live-rates">
            <div className="live-rate"><span className="key line" style={{ background: "var(--series-down)" }} />Down<strong>{live ? formatRate(live.down_bps) : "–"}</strong></div>
            <div className="live-rate"><span className="key line" style={{ background: "var(--series-up)" }} />Up<strong>{live ? formatRate(live.up_bps) : "–"}</strong></div>
          </div>
          <div className="conn">
            <span className="dot" style={{ background: connected ? "var(--good)" : "var(--critical)" }} />
            {connected ? "Live" : "Disconnected, retrying…"}
          </div>
          {status && <div className="mono">{status.interface} · {status.ip}</div>}
        </div>
      </nav>

      <main className="main">
        {problem && (
          <div className="banner" role="alert">
            <span aria-hidden="true">⚠</span>
            <div><strong>Monitoring is degraded</strong>{problem}</div>
          </div>
        )}
        {tab === "devices" && (
          <DevicesView devices={devices} status={status} selected={selected} onSelect={setSelected} onChange={loadDevices} />
        )}
        {tab === "traffic" && <TrafficView live={live} />}
        {tab === "alerts" && (
          <AlertsView alerts={alerts} devices={devices} onChange={loadAlerts}
            onOpenDevice={(mac) => { setSelected(mac); setTab("devices"); }} />
        )}
      </main>
    </div>
  );
}

function NavItem({ label, active, onClick, extra }: { label: string; active: boolean; onClick: () => void; extra?: ReactNode }) {
  return (
    <button className="nav-item" aria-current={active ? "page" : undefined} onClick={onClick}>
      {label}
      {extra}
    </button>
  );
}
