"use client";

import { useEffect, useState } from "react";

export function Countdown({ expiresAt, onExpire, size = 56 }: { expiresAt: string; onExpire?: () => void; size?: number }) {
  const [remainingMs, setRemainingMs] = useState(() => new Date(expiresAt).getTime() - Date.now());
  const totalMs = useState(() => Math.max(new Date(expiresAt).getTime() - Date.now(), 1))[0];

  useEffect(() => {
    const interval = setInterval(() => {
      const ms = new Date(expiresAt).getTime() - Date.now();
      setRemainingMs(ms);
      if (ms <= 0) {
        clearInterval(interval);
        onExpire?.();
      }
    }, 250);
    return () => clearInterval(interval);
  }, [expiresAt, onExpire]);

  const clamped = Math.max(remainingMs, 0);
  const seconds = Math.ceil(clamped / 1000);
  const mm = Math.floor(seconds / 60);
  const ss = seconds % 60;
  const fraction = Math.min(clamped / totalMs, 1);
  const isUrgent = seconds <= 30;

  const r = (size - 8) / 2;
  const circumference = 2 * Math.PI * r;

  return (
    <div className="relative" style={{ width: size, height: size }} role="timer" aria-live="polite" aria-label={`${mm}m ${ss}s remaining`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.08)" strokeWidth={4} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={isUrgent ? "#ef4444" : "#8b5cf6"}
          strokeWidth={4}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          strokeLinecap="round"
          className="transition-[stroke-dashoffset] duration-300 ease-linear"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-xs font-semibold tabular-nums text-white">
        {mm}:{ss.toString().padStart(2, "0")}
      </div>
    </div>
  );
}
