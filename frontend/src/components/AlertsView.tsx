import { useState } from "react";
import { api, type Alert, type Device } from "../api";
import { deviceName, formatAgo } from "../format";
import { SeverityBadge } from "./SeverityBadge";

type Props = { alerts: Alert[]; devices: Device[]; onChange: () => void; onOpenDevice: (mac: string) => void };

export function AlertsView({ alerts, devices, onChange, onOpenDevice }: Props) {
  const [filter, setFilter] = useState<"unread" | "all">("unread");
  const shown = filter === "unread" ? alerts.filter((a) => !a.acknowledged) : alerts;
  const byMac = new Map(devices.map((d) => [d.mac, d]));

  const ack = async (id: number) => { await api.ackAlert(id); onChange(); };
  const ackAll = async () => { await api.ackAll(); onChange(); };

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Alerts</h1>
          <p>New devices, router impersonation, port scans, risky ports and blocklisted domains.</p>
        </div>
        <div className="actions">
          <div className="segmented" role="group" aria-label="Filter">
            <button aria-pressed={filter === "unread"} onClick={() => setFilter("unread")}>Unread</button>
            <button aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All</button>
          </div>
          <button className="btn" onClick={ackAll} disabled={!alerts.some((a) => !a.acknowledged)}>
            Mark all read
          </button>
        </div>
      </header>

      <section className="card">
        {!shown.length ? (
          <div className="empty">{filter === "unread" ? "Nothing new. All quiet." : "No alerts yet."}</div>
        ) : (
          <ul className="alert-list">
            {shown.map((a) => {
              const device = a.mac ? byMac.get(a.mac) : undefined;
              return (
                <li key={a.id} className={`alert${a.acknowledged ? " read" : ""}`}>
                  <SeverityBadge severity={a.severity} />
                  <div>
                    <h3>{a.title}</h3>
                    {a.detail && <p>{a.detail}</p>}
                    <div className="alert-meta">
                      <span title={new Date(a.ts * 1000).toLocaleString()}>{formatAgo(a.ts)}</span>
                      {device && (
                        <button className="btn" style={{ padding: "2px 8px" }} onClick={() => onOpenDevice(device.mac)}>
                          View {deviceName(device)}
                        </button>
                      )}
                    </div>
                  </div>
                  {!a.acknowledged && (
                    <button className="btn" onClick={() => ack(a.id)}>Mark read</button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </>
  );
}
