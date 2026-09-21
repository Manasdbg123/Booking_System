"use client";

import { useMemo, useRef, useState } from "react";
import { cn, formatCurrency } from "@/lib/utils";

export type SeatState = "FREE" | "HELD" | "SOLD";

export type MapSeat = {
  id: string; // show_seat id
  seat_id: string;
  row_label: string;
  seat_number: number;
  section_id: string;
  section_name: string;
  section_color: string;
  price: number | string;
  status: SeatState;
  pos_x: number;
  pos_y: number;
  is_mine?: boolean;
};

const SEAT_SIZE = 10;

function statusVisual(seat: MapSeat, selected: boolean) {
  if (selected) return { fill: "#8b5cf6", pattern: "check", label: "Selected by you" };
  if (seat.is_mine) return { fill: "#8b5cf6", pattern: "check", label: "Held by you" };
  if (seat.status === "SOLD") return { fill: "#ef4444", pattern: "cross", label: "Sold" };
  if (seat.status === "HELD") return { fill: "#f59e0b", pattern: "stripe", label: "Held by another user" };
  return { fill: "none", pattern: "none", label: "Available" };
}

export function SeatMap({
  seats,
  selectedIds,
  onToggle,
  maxSelectable = 10,
}: {
  seats: MapSeat[];
  selectedIds: Set<string>;
  onToggle: (seat: MapSeat) => void;
  maxSelectable?: number;
}) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragState = useRef<{ startX: number; startY: number; ox: number; oy: number } | null>(null);
  const [hovered, setHovered] = useState<MapSeat | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);

  const bounds = useMemo(() => {
    const xs = seats.map((s) => s.pos_x);
    const ys = seats.map((s) => s.pos_y);
    return {
      minX: Math.min(...xs, 0) - 20,
      maxX: Math.max(...xs, 100) + 20,
      minY: Math.min(...ys, 0) - 20,
      maxY: Math.max(...ys, 100) + 20,
    };
  }, [seats]);

  const width = bounds.maxX - bounds.minX;
  const height = bounds.maxY - bounds.minY;

  // grid lookup for keyboard navigation
  const grid = useMemo(() => {
    const byRow = new Map<string, MapSeat[]>();
    for (const s of seats) {
      if (!byRow.has(s.row_label)) byRow.set(s.row_label, []);
      byRow.get(s.row_label)!.push(s);
    }
    for (const row of byRow.values()) row.sort((a, b) => a.seat_number - b.seat_number);
    return byRow;
  }, [seats]);
  const rowOrder = useMemo(() => Array.from(grid.keys()).sort(), [grid]);

  function moveFocus(seat: MapSeat, dRow: number, dCol: number) {
    const rowIdx = rowOrder.indexOf(seat.row_label);
    if (dCol !== 0) {
      const row = grid.get(seat.row_label)!;
      const idx = row.findIndex((s) => s.id === seat.id);
      const next = row[idx + dCol];
      if (next) {
        setFocusedId(next.id);
        document.getElementById(`seat-${next.id}`)?.focus();
      }
      return;
    }
    const nextRowLabel = rowOrder[rowIdx + dRow];
    if (!nextRowLabel) return;
    const row = grid.get(nextRowLabel)!;
    const idx = row.findIndex((s) => s.seat_number >= seat.seat_number);
    const next = row[Math.max(idx, 0)] ?? row[row.length - 1];
    if (next) {
      setFocusedId(next.id);
      document.getElementById(`seat-${next.id}`)?.focus();
    }
  }

  function handleWheel(e: React.WheelEvent) {
    e.preventDefault();
    const delta = -e.deltaY * 0.001;
    setScale((s) => Math.min(Math.max(s + delta, 0.5), 3));
  }

  function handlePointerDown(e: React.PointerEvent) {
    dragState.current = { startX: e.clientX, startY: e.clientY, ox: offset.x, oy: offset.y };
  }
  function handlePointerMove(e: React.PointerEvent) {
    if (!dragState.current) return;
    const dx = e.clientX - dragState.current.startX;
    const dy = e.clientY - dragState.current.startY;
    setOffset({ x: dragState.current.ox + dx, y: dragState.current.oy + dy });
  }
  function handlePointerUp() {
    dragState.current = null;
  }

  return (
    <div className="relative">
      <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-white/70">
        <LegendItem color="#2dd4bf" pattern="none" label="Available" />
        <LegendItem color="#8b5cf6" pattern="check" label="Your selection" />
        <LegendItem color="#f59e0b" pattern="stripe" label="Held by others" />
        <LegendItem color="#ef4444" pattern="cross" label="Sold" />
        <div className="ml-auto flex gap-2">
          <button
            aria-label="Zoom out"
            onClick={() => setScale((s) => Math.max(s - 0.2, 0.5))}
            className="rounded-lg border border-border px-2 py-1 hover:bg-white/5"
          >
            −
          </button>
          <button
            aria-label="Reset zoom"
            onClick={() => {
              setScale(1);
              setOffset({ x: 0, y: 0 });
            }}
            className="rounded-lg border border-border px-2 py-1 hover:bg-white/5"
          >
            Reset
          </button>
          <button
            aria-label="Zoom in"
            onClick={() => setScale((s) => Math.min(s + 0.2, 3))}
            className="rounded-lg border border-border px-2 py-1 hover:bg-white/5"
          >
            +
          </button>
        </div>
      </div>

      <div
        className="relative h-[420px] touch-none overflow-hidden rounded-2xl border border-border bg-surface/50 sm:h-[560px]"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <svg
          role="group"
          aria-label="Seat map"
          viewBox={`${bounds.minX} ${bounds.minY} ${width} ${height}`}
          width="100%"
          height="100%"
          style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`, transformOrigin: "center" }}
          className="transition-transform duration-75"
        >
          <defs>
            <pattern id="pat-stripe" patternUnits="userSpaceOnUse" width="4" height="4" patternTransform="rotate(45)">
              <rect width="4" height="4" fill="#f59e0b" />
              <line x1="0" y1="0" x2="0" y2="4" stroke="#7c3aed00" strokeWidth="0" />
              <line x1="0" y1="0" x2="0" y2="4" stroke="rgba(0,0,0,0.35)" strokeWidth="1.5" />
            </pattern>
          </defs>
          {seats.map((seat) => {
            const selected = selectedIds.has(seat.id);
            const visual = statusVisual(seat, selected);
            const disabled = seat.status !== "FREE" && !selected;
            return (
              <g
                key={seat.id}
                id={`seat-${seat.id}`}
                role="button"
                tabIndex={focusedId === seat.id || (!focusedId && seats[0]?.id === seat.id) ? 0 : -1}
                aria-label={`Row ${seat.row_label} seat ${seat.seat_number}, ${seat.section_name}, ${formatCurrency(seat.price)}, ${visual.label}`}
                aria-pressed={selected}
                aria-disabled={disabled}
                onFocus={() => setFocusedId(seat.id)}
                onMouseEnter={() => setHovered(seat)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => {
                  if (!disabled) onToggle(seat);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    if (!disabled) onToggle(seat);
                  } else if (e.key === "ArrowRight") moveFocus(seat, 0, 1);
                  else if (e.key === "ArrowLeft") moveFocus(seat, 0, -1);
                  else if (e.key === "ArrowDown") moveFocus(seat, 1, 0);
                  else if (e.key === "ArrowUp") moveFocus(seat, -1, 0);
                }}
                className={cn("cursor-pointer outline-none", disabled && "cursor-not-allowed")}
              >
                <rect
                  x={seat.pos_x}
                  y={seat.pos_y}
                  width={SEAT_SIZE}
                  height={SEAT_SIZE}
                  rx={3}
                  fill={visual.pattern === "stripe" ? "url(#pat-stripe)" : visual.fill === "none" ? "transparent" : visual.fill}
                  stroke={seat.section_color}
                  strokeWidth={selected ? 2.5 : 1.5}
                  className="transition-all duration-200"
                />
                {visual.pattern === "cross" && (
                  <path
                    d={`M${seat.pos_x + 2},${seat.pos_y + 2} L${seat.pos_x + 8},${seat.pos_y + 8} M${seat.pos_x + 8},${seat.pos_y + 2} L${seat.pos_x + 2},${seat.pos_y + 8}`}
                    stroke="white"
                    strokeWidth={1.2}
                  />
                )}
                {visual.pattern === "check" && (
                  <path d={`M${seat.pos_x + 2.5},${seat.pos_y + 5} L${seat.pos_x + 4.5},${seat.pos_y + 7.5} L${seat.pos_x + 8},${seat.pos_y + 3}`} stroke="white" strokeWidth={1.2} fill="none" />
                )}
                {focusedId === seat.id && (
                  <rect x={seat.pos_x - 2} y={seat.pos_y - 2} width={SEAT_SIZE + 4} height={SEAT_SIZE + 4} rx={5} fill="none" stroke="#a78bfa" strokeWidth={1} strokeDasharray="2,2" />
                )}
              </g>
            );
          })}
        </svg>

        {hovered && (
          <div className="pointer-events-none absolute left-3 top-3 rounded-xl border border-border bg-surface2/95 px-3 py-2 text-xs shadow-card">
            <p className="font-medium text-white">
              {hovered.row_label}
              {hovered.seat_number} · {hovered.section_name}
            </p>
            <p className="text-white/60">{formatCurrency(hovered.price)}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function LegendItem({ color, pattern, label }: { color: string; pattern: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="inline-block h-3 w-3 rounded-[3px] border border-white/20"
        style={{ background: pattern === "stripe" ? "repeating-linear-gradient(45deg,#f59e0b,#f59e0b 2px,#7c3aed11 2px,#7c3aed11 4px)" : pattern === "none" ? "transparent" : color }}
      />
      {label}
    </span>
  );
}
