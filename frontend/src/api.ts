export type Device = {
  mac: string;
  ip: string | null;
  hostname: string | null;
  vendor: string | null;
  label: string | null;
  category: string | null;
  trusted: boolean;
  notes: string | null;
  first_seen: number;
  last_seen: number;
  is_self: boolean;
  is_gateway: boolean;
  online: boolean;
};

export type Severity = "info" | "warning" | "serious" | "critical";

export type Alert = {
  id: number;
  ts: number;
  kind: string;
  severity: Severity;
  title: string;
  detail: string | null;
  mac: string | null;
  acknowledged: number;
};

export type TrafficPoint = { t: number; up: number; down: number };

export type Destination = {
  remote: string;
  domain: string | null;
  up: number;
  down: number;
  total: number;
  last_minute: number;
};

export type Traffic = {
  step_s: number;
  series: TrafficPoint[];
  destinations: Destination[];
  total_up: number;
  total_down: number;
};

export type Status = {
  interface: string;
  ip: string;
  mac: string;
  network: string;
  gateway: string | null;
  capturing: boolean;
  capture_error: string | null;
  scan_error: string | null;
  last_scan: number | null;
  blocklist_size: number;
};

export type Live = {
  t: number;
  up_bps: number;
  down_bps: number;
  alerts: { latest_id: number; unread: number };
  devices: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  status: () => request<Status>("/api/status"),
  devices: () => request<Device[]>("/api/devices"),
  updateDevice: (mac: string, fields: Partial<Pick<Device, "label" | "category" | "trusted" | "notes">>) =>
    request<Device>(`/api/devices/${encodeURIComponent(mac)}`, { method: "PATCH", body: JSON.stringify(fields) }),
  forgetDevice: (mac: string) => request(`/api/devices/${encodeURIComponent(mac)}`, { method: "DELETE" }),
  scan: () => request("/api/scan", { method: "POST" }),
  traffic: (minutes: number) => request<Traffic>(`/api/traffic?minutes=${minutes}`),
  alerts: () => request<Alert[]>("/api/alerts"),
  ackAlert: (id: number) => request(`/api/alerts/${id}/ack`, { method: "POST" }),
  ackAll: () => request("/api/alerts/ack-all", { method: "POST" }),
};

export function liveUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/live`;
}
