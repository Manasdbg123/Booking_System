"use client";

import { useEffect, useRef } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export type ShowEvent = {
  type: string;
  aggregate_type: string;
  aggregate_id: string;
  payload: Record<string, any>;
};

export function useShowSocket(showId: string | undefined, onEvent: (event: ShowEvent) => void) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!showId) return;
    let ws: WebSocket | null = null;
    let closedByUs = false;
    let retryDelay = 1000;

    function connect() {
      ws = new WebSocket(`${WS_URL}/ws/shows/${showId}`);
      ws.onmessage = (msg) => {
        try {
          handlerRef.current(JSON.parse(msg.data));
        } catch {
          /* ignore malformed message */
        }
      };
      ws.onclose = () => {
        if (closedByUs) return;
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, 10000);
      };
    }
    connect();

    return () => {
      closedByUs = true;
      ws?.close();
    };
  }, [showId]);
}
