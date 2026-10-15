import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { TrafficPoint } from "../api";
import { formatRate, formatTime } from "../format";

const HEIGHT = 260;
const M = { top: 12, right: 92, bottom: 26, left: 64 };
const SERIES = [
  { key: "down", label: "Download", color: "var(--series-down)" },
  { key: "up", label: "Upload", color: "var(--series-up)" },
] as const;

function niceMax(value: number, ticks = 4): number {
  if (value <= 0) return 1000;
  const raw = value / ticks;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw)!;
  return step * ticks;
}

type Props = { series: TrafficPoint[]; stepSeconds: number; spansDays: boolean };

/** Upload vs download rate over time: two lines on one shared axis, crosshair tooltip on hover. */
export function TrafficChart({ series, stepSeconds, spansDays }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(320, entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const rates = useMemo(
    () => series.map((p) => ({ t: p.t, up: p.up / stepSeconds, down: p.down / stepSeconds })),
    [series, stepSeconds],
  );

  const innerW = width - M.left - M.right;
  const innerH = HEIGHT - M.top - M.bottom;
  const yMax = niceMax(Math.max(0, ...rates.map((r) => Math.max(r.up, r.down))));
  const x = (i: number) => M.left + (rates.length <= 1 ? 0 : (i / (rates.length - 1)) * innerW);
  const y = (v: number) => M.top + innerH - (v / yMax) * innerH;

  const paths = SERIES.map((s) => ({
    ...s,
    d: rates.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r[s.key]).toFixed(1)}`).join(""),
  }));

  const yTicks = [0, 1, 2, 3, 4].map((i) => (yMax / 4) * i);
  const xTickCount = Math.min(6, rates.length);
  const xTicks = Array.from({ length: xTickCount }, (_, i) =>
    Math.round((i / Math.max(1, xTickCount - 1)) * (rates.length - 1)),
  );

  // End labels only when the two line ends are far enough apart not to collide;
  // otherwise the legend and tooltip carry identity.
  const last = rates[rates.length - 1];
  const showEndLabels = last !== undefined && Math.abs(y(last.up) - y(last.down)) >= 16;

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - box.left;
    const i = Math.round((px / box.width) * (rates.length - 1));
    setHover(Math.max(0, Math.min(rates.length - 1, i)));
  };

  const hovered = hover !== null ? rates[hover] : null;
  const tooltipLeft = hover !== null ? Math.min(x(hover) + 12, width - 180) : 0;

  return (
    <div className="chart" ref={wrapRef}>
      <svg height={HEIGHT} role="img" aria-label="Upload and download rate over time">
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={M.left} x2={M.left + innerW} y1={y(v)} y2={y(v)}
              stroke={v === 0 ? "var(--baseline)" : "var(--grid)"} strokeWidth={1} />
            <text x={M.left - 8} y={y(v)} dy="0.32em" textAnchor="end">{formatRate(v)}</text>
          </g>
        ))}
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={HEIGHT - 6}
            textAnchor={i === 0 ? "start" : i === rates.length - 1 ? "end" : "middle"}>
            {formatTime(rates[i].t, spansDays)}
          </text>
        ))}

        {paths.map((p) => (
          <path key={p.key} d={p.d} fill="none" stroke={p.color} strokeWidth={2}
            strokeLinejoin="round" strokeLinecap="round" />
        ))}

        {last && showEndLabels &&
          SERIES.map((s) => (
            <g key={s.key}>
              <circle cx={x(rates.length - 1)} cy={y(last[s.key])} r={4} fill={s.color}
                stroke="var(--surface)" strokeWidth={2} />
              <text className="end-label" x={x(rates.length - 1) + 10} y={y(last[s.key])} dy="0.32em">
                {s.label}
              </text>
            </g>
          ))}

        {hovered && hover !== null && (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={M.top + innerH} stroke="var(--baseline)" />
            {SERIES.map((s) => (
              <circle key={s.key} cx={x(hover)} cy={y(hovered[s.key])} r={4.5} fill={s.color}
                stroke="var(--surface)" strokeWidth={2} />
            ))}
          </g>
        )}

        <rect x={M.left} y={M.top} width={innerW} height={innerH} fill="transparent"
          onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>

      {hovered && (
        <div className="tooltip" style={{ left: tooltipLeft, top: M.top }}>
          <div className="tooltip-time">{formatTime(hovered.t, spansDays)}</div>
          {SERIES.map((s) => (
            <div className="tooltip-row" key={s.key}>
              <span className="key line" style={{ background: s.color }} />
              {s.label}
              <strong>{formatRate(hovered[s.key])}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TrafficLegend() {
  return (
    <div className="legend">
      {SERIES.map((s) => (
        <span key={s.key}>
          <span className="key line" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}
