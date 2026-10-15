import type { Severity } from "../api";

const META: Record<Severity, { label: string; color: string }> = {
  info: { label: "Info", color: "var(--accent)" },
  warning: { label: "Warning", color: "var(--warning)" },
  serious: { label: "Serious", color: "var(--serious)" },
  critical: { label: "Critical", color: "var(--critical)" },
};

/** Status is never color-only: each severity has its own icon shape and a text label. */
function Icon({ severity, color }: { severity: Severity; color: string }) {
  switch (severity) {
    case "info":
      return (
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="7" fill={color} />
          <rect x="7.1" y="7" width="1.8" height="5" rx=".9" fill="#fff" />
          <circle cx="8" cy="4.6" r="1.1" fill="#fff" />
        </svg>
      );
    case "warning":
      return (
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M8 1.2 15.2 14H.8z" fill={color} strokeLinejoin="round" />
          <rect x="7.1" y="5.5" width="1.8" height="4.6" rx=".9" fill="#1a1a19" />
          <circle cx="8" cy="12" r="1" fill="#1a1a19" />
        </svg>
      );
    case "serious":
      return (
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M8 .8 15.2 8 8 15.2.8 8z" fill={color} />
          <rect x="7.1" y="4" width="1.8" height="5" rx=".9" fill="#fff" />
          <circle cx="8" cy="11.2" r="1" fill="#fff" />
        </svg>
      );
    case "critical":
      return (
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M5 .8h6L15.2 5v6L11 15.2H5L.8 11V5z" fill={color} />
          <path d="m5.5 5.5 5 5m0-5-5 5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      );
  }
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const meta = META[severity];
  return (
    <span className="severity">
      <Icon severity={severity} color={meta.color} />
      {meta.label}
    </span>
  );
}
