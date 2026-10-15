import { useCallback, useEffect, useState } from "react";
import { api, type Live, type Traffic } from "../api";
import { formatBytes, formatRate } from "../format";
import { TrafficChart, TrafficLegend } from "./TrafficChart";

const RANGES = [
  { label: "15 min", minutes: 15 },
  { label: "1 hour", minutes: 60 },
  { label: "6 hours", minutes: 360 },
  { label: "24 hours", minutes: 1440 },
  { label: "7 days", minutes: 10080 },
];
const REFRESH_MS = 15_000;

export function TrafficView({ live }: { live: Live | null }) {
  const [minutes, setMinutes] = useState(60);
  const [view, setView] = useState<"chart" | "table">("chart");
  const [data, setData] = useState<Traffic | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.traffic(minutes).then(
      (d) => { setData(d); setError(null); },
      (e: Error) => setError(e.message),
    );
  }, [minutes]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const rangeLabel = RANGES.find((r) => r.minutes === minutes)?.label.replace(/^1 /, "") ?? "";
  const maxDest = Math.max(1, ...(data?.destinations.map((d) => d.total) ?? []));

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Traffic</h1>
          <p>Everything this laptop sends and receives on the watched interface.</p>
        </div>
        <div className="segmented" role="group" aria-label="Time range">
          {RANGES.map((r) => (
            <button key={r.minutes} aria-pressed={r.minutes === minutes} onClick={() => setMinutes(r.minutes)}>
              {r.label}
            </button>
          ))}
        </div>
      </header>

      {error && <div className="banner">Couldn't load traffic: {error}</div>}

      <div className="stack">
        <div className="tiles">
          <Tile label="Download now" color="var(--series-down)" value={live ? formatRate(live.down_bps) : "–"} />
          <Tile label="Upload now" color="var(--series-up)" value={live ? formatRate(live.up_bps) : "–"} />
          <Tile label={`Downloaded, last ${rangeLabel}`} value={data ? formatBytes(data.total_down) : "–"} />
          <Tile label={`Uploaded, last ${rangeLabel}`} value={data ? formatBytes(data.total_up) : "–"} />
        </div>

        <section className="card">
          <div className="card-head">
            <h2>Rate over time</h2>
            <div className="actions">
              <TrafficLegend />
              <div className="segmented" role="group" aria-label="Display">
                <button aria-pressed={view === "chart"} onClick={() => setView("chart")}>Chart</button>
                <button aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button>
              </div>
            </div>
          </div>
          <div className="card-body">
            {!data ? (
              <div className="empty">Loading…</div>
            ) : view === "chart" ? (
              <TrafficChart series={data.series} stepSeconds={data.step_s} spansDays={minutes > 1440} />
            ) : (
              <SeriesTable data={data} spansDays={minutes > 1440} />
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2>Top destinations</h2>
            <span className="sub">by total bytes, last {rangeLabel}</span>
          </div>
          <div className="card-body table-wrap">
            {!data?.destinations.length ? (
              <div className="empty">No traffic recorded in this range yet.</div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Destination</th>
                    <th style={{ width: "40%" }}>Share</th>
                    <th className="num">Download</th>
                    <th className="num">Upload</th>
                  </tr>
                </thead>
                <tbody>
                  {data.destinations.map((d) => (
                    <tr key={d.remote}>
                      <td>
                        <div>{d.domain ?? d.remote}</div>
                        {d.domain && <div className="sub mono">{d.remote}</div>}
                      </td>
                      <td>
                        <div className="bar" title={`Download ${formatBytes(d.down)} · Upload ${formatBytes(d.up)}`}>
                          {d.down > 0 && <span style={{ width: `${(d.down / maxDest) * 100}%`, background: "var(--series-down)" }} />}
                          {d.up > 0 && <span style={{ width: `${(d.up / maxDest) * 100}%`, background: "var(--series-up)" }} />}
                        </div>
                      </td>
                      <td className="num">{formatBytes(d.down)}</td>
                      <td className="num">{formatBytes(d.up)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

function Tile({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="card tile">
      <div className="tile-label">
        {color && <span className="key line" style={{ background: color }} />}
        {label}
      </div>
      <div className="tile-value">{value}</div>
    </div>
  );
}

function SeriesTable({ data, spansDays }: { data: Traffic; spansDays: boolean }) {
  const rows = data.series.filter((p) => p.up || p.down).reverse();
  if (!rows.length) return <div className="empty">No traffic recorded in this range yet.</div>;
  return (
    <div className="table-wrap" style={{ maxHeight: 320, overflowY: "auto" }}>
      <table className="table">
        <thead>
          <tr><th>Time</th><th className="num">Download</th><th className="num">Upload</th></tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.t}>
              <td>{new Date(p.t * 1000).toLocaleString([], spansDays ? undefined : { hour: "2-digit", minute: "2-digit" })}</td>
              <td className="num">{formatBytes(p.down)}</td>
              <td className="num">{formatBytes(p.up)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
