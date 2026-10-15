import { useEffect, useState } from "react";
import { liveUrl, type Live } from "./api";

/** Subscribes to the backend's live feed, reconnecting if the container restarts. */
export function useLive(): { live: Live | null; connected: boolean } {
  const [live, setLive] = useState<Live | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(liveUrl());
      ws.onopen = () => setConnected(true);
      ws.onmessage = (e) => setLive(JSON.parse(e.data) as Live);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = window.setTimeout(connect, 2000);
      };
    };
    connect();

    return () => {
      closed = true;
      window.clearTimeout(retry);
      ws?.close();
    };
  }, []);

  return { live, connected };
}
