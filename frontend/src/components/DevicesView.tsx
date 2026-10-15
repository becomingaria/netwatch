import { useEffect, useMemo, useState } from "react";
import { api, type Device, type Status } from "../api";
import { deviceName, formatAgo } from "../format";

export const CATEGORIES = [
  "Computer", "Phone", "Tablet", "TV / media", "Smart speaker", "Camera",
  "Smart home / IoT", "Game console", "Printer", "Network gear", "Other",
];

type Filter = "all" | "online" | "untrusted";
type Props = {
  devices: Device[];
  status: Status | null;
  selected: string | null;
  onSelect: (mac: string | null) => void;
  onChange: () => void;
};

export function DevicesView({ devices, status, selected, onSelect, onChange }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [scanning, setScanning] = useState(false);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return devices
      .filter((d) => (filter === "online" ? d.online : filter === "untrusted" ? !d.trusted : true))
      .filter((d) =>
        !q || [d.label, d.hostname, d.ip, d.mac, d.vendor, d.category].some((v) => v?.toLowerCase().includes(q)),
      )
      .sort((a, b) => Number(b.online) - Number(a.online) || (a.ip ?? "").localeCompare(b.ip ?? "", undefined, { numeric: true }));
  }, [devices, query, filter]);

  const selectedDevice = devices.find((d) => d.mac === selected) ?? null;
  const onlineCount = devices.filter((d) => d.online).length;

  const scan = async () => {
    setScanning(true);
    await api.scan();
    window.setTimeout(() => { setScanning(false); onChange(); }, 8000);
  };

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Devices</h1>
          <p>
            {onlineCount} online of {devices.length} seen on {status?.network ?? "your network"}
            {status?.last_scan ? ` · last scan ${formatAgo(status.last_scan)}` : ""}
          </p>
        </div>
        <div className="actions">
          <input className="input search" type="search" placeholder="Search name, IP, MAC, maker…"
            value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search devices" />
          <div className="segmented" role="group" aria-label="Filter">
            {(["all", "online", "untrusted"] as const).map((f) => (
              <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f[0].toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
          <button className="btn primary" onClick={scan} disabled={scanning}>
            {scanning ? "Scanning…" : "Scan now"}
          </button>
        </div>
      </header>

      <div className={selectedDevice ? "split" : undefined}>
        <section className="card table-wrap">
          {!shown.length ? (
            <div className="empty">
              {devices.length ? "No devices match." : "No devices yet. The first scan runs at startup and takes a few seconds."}
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Device</th>
                  <th>Maker</th>
                  <th>IP</th>
                  <th>MAC</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((d) => (
                  <tr key={d.mac} className="clickable" aria-selected={d.mac === selected}
                    onClick={() => onSelect(d.mac === selected ? null : d.mac)}>
                    <td>
                      <span className="state">
                        <span className="dot" style={{ background: d.online ? "var(--good)" : "var(--baseline)" }} />
                        {d.online ? "Online" : "Offline"}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                        <span style={{ fontWeight: d.label ? 600 : 400 }}>{deviceName(d)}</span>
                        {d.is_self && <span className="tag accent">This laptop</span>}
                        {d.is_gateway && <span className="tag accent">Router</span>}
                        {!d.trusted && !d.is_self && <span className="tag">Unreviewed</span>}
                      </div>
                      {d.category && <div className="sub">{d.category}</div>}
                    </td>
                    <td>{d.vendor ?? <span className="sub">{isRandomized(d.mac) ? "Private MAC" : "Unknown"}</span>}</td>
                    <td className="mono">{d.ip ?? "–"}</td>
                    <td className="mono">{d.mac}</td>
                    <td className="sub" title={new Date(d.last_seen * 1000).toLocaleString()}>{formatAgo(d.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {selectedDevice && (
          <DeviceEditor key={selectedDevice.mac} device={selectedDevice} onClose={() => onSelect(null)} onChange={onChange} />
        )}
      </div>
    </>
  );
}

function isRandomized(mac: string): boolean {
  return (parseInt(mac.slice(0, 2), 16) & 0x02) !== 0;
}

function DeviceEditor({ device, onClose, onChange }: { device: Device; onClose: () => void; onChange: () => void }) {
  const [label, setLabel] = useState(device.label ?? "");
  const [category, setCategory] = useState(device.category ?? "");
  const [notes, setNotes] = useState(device.notes ?? "");
  const [trusted, setTrusted] = useState(device.trusted);
  const [saving, setSaving] = useState(false);

  useEffect(() => setTrusted(device.trusted), [device.trusted]);

  const dirty =
    label !== (device.label ?? "") || category !== (device.category ?? "") ||
    notes !== (device.notes ?? "") || trusted !== device.trusted;

  const save = async () => {
    setSaving(true);
    await api.updateDevice(device.mac, { label: label || null, category: category || null, notes: notes || null, trusted });
    setSaving(false);
    onChange();
  };

  const forget = async () => {
    if (!confirm(`Forget ${deviceName(device)}? It will reappear (and alert again) if it is seen on the network.`)) return;
    await api.forgetDevice(device.mac);
    onClose();
    onChange();
  };

  return (
    <aside className="card editor">
      <div className="card-head">
        <h2>{deviceName(device)}</h2>
        <button className="btn" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="card-body">
        <label className="field">
          <span>Label</span>
          <input className="input" value={label} placeholder={device.hostname ?? "e.g. Living room TV"}
            onChange={(e) => setLabel(e.target.value)} />
        </label>
        <label className="field">
          <span>Category</span>
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Uncategorised</option>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={trusted} onChange={(e) => setTrusted(e.target.checked)} />
          I recognise this device (trusted)
        </label>
        <label className="field">
          <span>Notes</span>
          <textarea className="textarea" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>

        <dl className="facts">
          <dt>Hostname</dt><dd>{device.hostname ?? "–"}</dd>
          <dt>Maker</dt><dd>{device.vendor ?? (isRandomized(device.mac) ? "Private (randomized) MAC" : "Unknown")}</dd>
          <dt>IP</dt><dd className="mono">{device.ip ?? "–"}</dd>
          <dt>MAC</dt><dd className="mono">{device.mac}</dd>
          <dt>First seen</dt><dd>{new Date(device.first_seen * 1000).toLocaleString()}</dd>
          <dt>Last seen</dt><dd>{new Date(device.last_seen * 1000).toLocaleString()}</dd>
        </dl>

        <div className="actions">
          <button className="btn primary" onClick={save} disabled={!dirty || saving}>{saving ? "Saving…" : "Save"}</button>
          <button className="btn danger" onClick={forget} style={{ marginLeft: "auto" }}>Forget device</button>
        </div>
      </div>
    </aside>
  );
}
