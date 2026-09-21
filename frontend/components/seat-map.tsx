"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

export type MapSection = { id: string; name: string; base_price: number | string; color: string };

const SEAT_W = 10;
const PAD = 40;

type Visual = { fill: string; stroke: string; glyph: "none" | "cross" | "check"; label: string };

function visualFor(seat: MapSeat, selected: boolean): Visual {
  if (selected) return { fill: "#8b5cf6", stroke: "#c4b5fd", glyph: "check", label: "selected by you" };
  if (seat.is_mine) return { fill: "#7c3aed", stroke: "#a78bfa", glyph: "check", label: "held by you" };
  if (seat.status === "SOLD") return { fill: "#3f1d2e", stroke: "#8b2f4a", glyph: "cross", label: "sold" };
  if (seat.status === "HELD") return { fill: "#4a3410", stroke: "#f59e0b", glyph: "none", label: "held by someone else" };
  // available: tinted by its section so pricing zones read at a glance
  return { fill: "rgba(255,255,255,0.10)", stroke: seat.section_color, glyph: "none", label: "available" };
}

export function SeatMap({
  seats,
  sections,
  selectedIds,
  onToggle,
  maxSelectable = 8,
}: {
  seats: MapSeat[];
  sections: MapSection[];
  selectedIds: Set<string>;
  onToggle: (seat: MapSeat) => void;
  maxSelectable?: number;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState<{ seat: MapSeat; x: number; y: number } | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [dimmedSection, setDimmedSection] = useState<string | null>(null);
  const panState = useRef<{ startX: number; startY: number; ox: number; oy: number } | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);

  const bounds = useMemo(() => {
    if (seats.length === 0) return { minX: 0, minY: 0, w: 100, h: 100 };
    const xs = seats.map((s) => s.pos_x);
    const ys = seats.map((s) => s.pos_y);
    const minX = Math.min(...xs) - PAD;
    const minY = Math.min(...ys) - PAD * 2.2; // extra headroom for the stage
    return {
      minX,
      minY,
      w: Math.max(...xs) + SEAT_W + PAD - minX,
      h: Math.max(...ys) + SEAT_W + PAD - minY,
    };
  }, [seats]);

  // Row label anchors: leftmost seat of each row.
  const rowAnchors = useMemo(() => {
    const byRow = new Map<string, MapSeat>();
    for (const s of seats) {
      const current = byRow.get(s.row_label);
      if (!current || s.pos_x < current.pos_x) byRow.set(s.row_label, s);
    }
    return Array.from(byRow.values());
  }, [seats]);

  // Grid for keyboard navigation.
  const grid = useMemo(() => {
    const byRow = new Map<string, MapSeat[]>();
    for (const s of seats) {
      if (!byRow.has(s.row_label)) byRow.set(s.row_label, []);
      byRow.get(s.row_label)!.push(s);
    }
    for (const row of byRow.values()) row.sort((a, b) => a.seat_number - b.seat_number);
    return byRow;
  }, [seats]);
  const rowOrder = useMemo(() => Array.from(grid.keys()), [grid]);

  const focusSeat = useCallback((seat: MapSeat | undefined) => {
    if (!seat) return;
    setFocusedId(seat.id);
    document.getElementById(`seat-${seat.id}`)?.focus();
  }, []);

  function moveFocus(seat: MapSeat, dRow: number, dCol: number) {
    if (dCol !== 0) {
      const row = grid.get(seat.row_label)!;
      const i = row.findIndex((s) => s.id === seat.id);
      focusSeat(row[i + dCol]);
      return;
    }
    const nextRow = grid.get(rowOrder[rowOrder.indexOf(seat.row_label) + dRow] ?? "");
    if (!nextRow) return;
    focusSeat(nextRow.find((s) => s.seat_number >= seat.seat_number) ?? nextRow[nextRow.length - 1]);
  }

  // Wheel zoom, bound non-passively so preventDefault actually works.
  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && Math.abs(e.deltaY) < 2) return;
      e.preventDefault();
      setZoom((z) => Math.min(Math.max(z - e.deltaY * 0.0015, 0.6), 6));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Fit-to-frame renders a 5,000-seat hall at ~3px per seat, which is far
  // too small to tap on a phone. Start zoomed in far enough that a seat is
  // at least MIN_SEAT_PX across and let the user pan, rather than showing
  // an unusable whole-hall view.
  useEffect(() => {
    const el = frameRef.current;
    if (!el || seats.length === 0) return;
    const frameWidth = el.clientWidth;
    if (!frameWidth) return;
    const frameHeight = el.clientHeight;

    // A fingertip needs a much bigger target than a cursor. On touch we
    // zoom in until seats clear ~13px; with a mouse a smaller seat is still
    // comfortably clickable, so we stay closer to the whole-hall overview.
    const coarsePointer = window.matchMedia?.("(pointer: coarse)").matches ?? false;
    const minSeatPx = coarsePointer ? 13 : 8;

    const seatPxAtFit = (frameWidth / bounds.w) * SEAT_W;
    if (seatPxAtFit >= minSeatPx) return;

    const initialZoom = Math.min(minSeatPx / seatPxAtFit, 6);
    setZoom(initialZoom);

    // Park the stage just under the top edge so the first thing you see is
    // the stage and the front rows. The CSS transform scales about the
    // frame's centre, so this maps the stage's SVG y through the viewBox
    // fit-scale and then through the zoom to land it at TOP_MARGIN px.
    const TOP_MARGIN = 22;
    const fitScale = Math.min(frameWidth / bounds.w, frameHeight / bounds.h);
    // bounds.minY already reserves headroom above the first row for the
    // stage, so aligning the content's top edge brings the stage into view.
    const stageSvgY = bounds.minY;
    const stageYBeforeZoom = frameHeight / 2 + (stageSvgY - (bounds.minY + bounds.h / 2)) * fitScale;
    setPan({ x: 0, y: TOP_MARGIN - frameHeight / 2 - (stageYBeforeZoom - frameHeight / 2) * initialZoom });
    // Intentionally keyed on the map's identity only: re-running on every
    // seat status change would yank the view back while the user is panning.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bounds.w, seats.length]);

  // Pinch-to-zoom.
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinchStart = useRef<{ dist: number; zoom: number } | null>(null);

  function trackPointer(e: React.PointerEvent) {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
  }
  function pinchDistance(): number | null {
    const pts = Array.from(pointers.current.values());
    if (pts.length < 2) return null;
    return Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
  }

  // Panning starts only on the background, never on a seat, so a click on a
  // seat is never swallowed by a stray drag.
  //
  // Deliberately no setPointerCapture here: capturing on this container
  // retargets the subsequent pointerup, which stops the browser from
  // synthesising a click on the seat that was pressed — seats became
  // unselectable by mouse while still working by keyboard.
  function onBackgroundPointerDown(e: React.PointerEvent) {
    trackPointer(e);
    const dist = pinchDistance();
    if (dist) {
      pinchStart.current = { dist, zoom };
      panState.current = null;
      return;
    }
    if ((e.target as Element).closest?.('[role="gridcell"]')) return;
    panState.current = { startX: e.clientX, startY: e.clientY, ox: pan.x, oy: pan.y };
  }

  function onPointerMove(e: React.PointerEvent) {
    if (pointers.current.has(e.pointerId)) trackPointer(e);

    if (pinchStart.current) {
      const dist = pinchDistance();
      if (dist) setZoom(Math.min(Math.max((dist / pinchStart.current.dist) * pinchStart.current.zoom, 0.6), 6));
      return;
    }
    if (!panState.current) return;
    setPan({
      x: panState.current.ox + (e.clientX - panState.current.startX),
      y: panState.current.oy + (e.clientY - panState.current.startY),
    });
  }

  function endPan(e?: React.PointerEvent) {
    if (e) pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinchStart.current = null;
    panState.current = null;
  }

  const reset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const stageWidth = bounds.w * 0.52;
  const stageX = bounds.minX + bounds.w / 2 - stageWidth / 2;
  const stageY = bounds.minY + 14;

  return (
    <div className="flex flex-col gap-3">
      {/* Price legend — colour per section, with its price */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-border bg-surface/60 px-4 py-3">
        {sections.map((s) => (
          <button
            key={s.id}
            onMouseEnter={() => setDimmedSection(s.id)}
            onMouseLeave={() => setDimmedSection(null)}
            onFocus={() => setDimmedSection(s.id)}
            onBlur={() => setDimmedSection(null)}
            className="flex items-center gap-2 rounded-lg px-1 py-0.5 text-xs text-white/75 transition hover:text-white"
          >
            <span className="h-3 w-3 rounded-[3px] border-2" style={{ borderColor: s.color, background: `${s.color}22` }} />
            <span className="font-medium">{s.name}</span>
            <span className="tabular-nums text-white/45">{formatCurrency(s.base_price)}</span>
          </button>
        ))}
        <span className="mx-1 hidden h-4 w-px bg-border sm:block" />
        <LegendChip label="Selected" fill="#8b5cf6" stroke="#c4b5fd" glyph="check" />
        <LegendChip label="Held" fill="#4a3410" stroke="#f59e0b" />
        <LegendChip label="Sold" fill="#3f1d2e" stroke="#8b2f4a" glyph="cross" />
      </div>

      <div
        ref={frameRef}
        data-seatmap-frame
        className="relative h-[460px] touch-none overflow-hidden rounded-2xl border border-border bg-[radial-gradient(ellipse_at_top,rgba(139,92,246,0.10),transparent_65%)] sm:h-[620px]"
      >
        {/* zoom controls */}
        <div className="absolute right-3 top-3 z-10 flex gap-1 rounded-lg border border-border bg-surface/90 p-1 backdrop-blur">
          <IconBtn label="Zoom out" onClick={() => setZoom((z) => Math.max(z - 0.3, 0.6))}>−</IconBtn>
          <IconBtn label="Reset view" onClick={reset}>
            <span className="text-[11px] leading-none">Fit</span>
          </IconBtn>
          <IconBtn label="Zoom in" onClick={() => setZoom((z) => Math.min(z + 0.3, 6))}>+</IconBtn>
        </div>
        <p className="pointer-events-none absolute bottom-3 left-3 z-10 rounded-full border border-border/60 bg-surface/85 px-2.5 py-1 text-[11px] text-white/45 backdrop-blur">
          <span className="hidden sm:inline">Scroll to zoom · drag to pan · arrow keys to move, Enter to select</span>
          <span className="sm:hidden">Pinch to zoom · drag to pan</span>
        </p>

        <div
          className="h-full w-full cursor-grab active:cursor-grabbing"
          onPointerDown={onBackgroundPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endPan}
          onPointerLeave={endPan}
        >
          <svg
            role="grid"
            aria-label="Seat map"
            viewBox={`${bounds.minX} ${bounds.minY} ${bounds.w} ${bounds.h}`}
            width="100%"
            height="100%"
            style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
            className="transition-transform duration-100 ease-out"
          >
            <defs>
              <linearGradient id="stage-glow" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#a78bfa" stopOpacity="0" />
              </linearGradient>
            </defs>

            {/* Stage */}
            <path
              d={`M ${stageX} ${stageY + 16} Q ${stageX + stageWidth / 2} ${stageY - 12} ${stageX + stageWidth} ${stageY + 16}`}
              fill="none"
              stroke="#a78bfa"
              strokeWidth={2.5}
              strokeLinecap="round"
            />
            <rect x={stageX} y={stageY + 16} width={stageWidth} height={26} fill="url(#stage-glow)" />
            <text
              x={stageX + stageWidth / 2}
              y={stageY + 9}
              textAnchor="middle"
              className="fill-white/70"
              style={{ fontSize: 11, letterSpacing: 4, fontWeight: 600 }}
            >
              STAGE
            </text>

            {/* Row labels, both sides */}
            {rowAnchors.map((s) => (
              <g key={`row-${s.row_label}`} className="pointer-events-none">
                <text
                  x={s.pos_x - 14}
                  y={s.pos_y + SEAT_W - 1.5}
                  textAnchor="end"
                  className="fill-white/30"
                  style={{ fontSize: 7.5, fontWeight: 600 }}
                >
                  {s.row_label}
                </text>
              </g>
            ))}

            {/* Seats */}
            {seats.map((seat) => {
              const selected = selectedIds.has(seat.id);
              const v = visualFor(seat, selected);
              const disabled = seat.status !== "FREE" && !selected && !seat.is_mine;
              const dimmed = dimmedSection !== null && seat.section_id !== dimmedSection;
              const isFocused = focusedId === seat.id;
              return (
                <g
                  key={seat.id}
                  id={`seat-${seat.id}`}
                  role="gridcell"
                  tabIndex={isFocused || (!focusedId && seats[0]?.id === seat.id) ? 0 : -1}
                  aria-label={`Row ${seat.row_label} seat ${seat.seat_number}, ${seat.section_name}, ${formatCurrency(seat.price)}, ${v.label}`}
                  aria-selected={selected}
                  aria-disabled={disabled}
                  opacity={dimmed ? 0.18 : 1}
                  onFocus={() => setFocusedId(seat.id)}
                  onPointerEnter={(e) => {
                    const rect = frameRef.current?.getBoundingClientRect();
                    setHovered({ seat, x: e.clientX - (rect?.left ?? 0), y: e.clientY - (rect?.top ?? 0) });
                  }}
                  onPointerLeave={() => setHovered(null)}
                  onClick={(e) => {
                    e.stopPropagation();
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
                  className={cn("outline-none", disabled ? "cursor-not-allowed" : "cursor-pointer")}
                >
                  <rect
                    x={seat.pos_x}
                    y={seat.pos_y}
                    width={SEAT_W}
                    height={SEAT_W - 1}
                    rx={2.5}
                    fill={v.fill}
                    stroke={v.stroke}
                    strokeWidth={selected || seat.is_mine ? 1.6 : 0.9}
                    className="transition-[fill,stroke,transform] duration-150"
                    style={{ transformOrigin: `${seat.pos_x + SEAT_W / 2}px ${seat.pos_y + SEAT_W / 2}px`, transform: selected ? "scale(1.18)" : undefined }}
                  />
                  {v.glyph === "cross" && (
                    <path
                      d={`M${seat.pos_x + 3},${seat.pos_y + 3} L${seat.pos_x + 7},${seat.pos_y + 6.5} M${seat.pos_x + 7},${seat.pos_y + 3} L${seat.pos_x + 3},${seat.pos_y + 6.5}`}
                      stroke="#e06b8b"
                      strokeWidth={1}
                      strokeLinecap="round"
                      className="pointer-events-none"
                    />
                  )}
                  {v.glyph === "check" && (
                    <path
                      d={`M${seat.pos_x + 2.6},${seat.pos_y + 4.8} L${seat.pos_x + 4.4},${seat.pos_y + 6.6} L${seat.pos_x + 7.4},${seat.pos_y + 2.8}`}
                      stroke="#fff"
                      strokeWidth={1.3}
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="pointer-events-none"
                    />
                  )}
                  {isFocused && (
                    <rect
                      x={seat.pos_x - 2.5}
                      y={seat.pos_y - 2.5}
                      width={SEAT_W + 5}
                      height={SEAT_W + 4}
                      rx={4.5}
                      fill="none"
                      stroke="#e9d5ff"
                      strokeWidth={1}
                      className="pointer-events-none"
                    />
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        {/* Hover preview follows the cursor */}
        {hovered && (
          <div
            className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-[calc(100%+12px)] whitespace-nowrap rounded-lg border border-border bg-surface2/95 px-2.5 py-1.5 shadow-card backdrop-blur"
            style={{ left: hovered.x, top: hovered.y }}
          >
            <p className="text-xs font-semibold text-white">
              {hovered.seat.row_label}
              {hovered.seat.seat_number}
              <span className="ml-1.5 font-normal text-white/50">{hovered.seat.section_name}</span>
            </p>
            <p className="text-[11px] tabular-nums text-accent-glow">
              {formatCurrency(hovered.seat.price)}
              {hovered.seat.status !== "FREE" && <span className="ml-1.5 text-white/40">· {visualFor(hovered.seat, false).label}</span>}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function IconBtn({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      aria-label={label}
      onClick={onClick}
      className="flex h-7 w-8 items-center justify-center rounded-md text-sm text-white/70 transition hover:bg-white/10 hover:text-white"
    >
      {children}
    </button>
  );
}

function LegendChip({ label, fill, stroke, glyph }: { label: string; fill: string; stroke: string; glyph?: "check" | "cross" }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-white/60">
      <span className="relative h-3 w-3 rounded-[3px] border" style={{ background: fill, borderColor: stroke }}>
        {glyph === "check" && (
          <svg viewBox="0 0 12 12" className="absolute inset-0">
            <path d="M3 6.2 L5 8.4 L9 3.6" stroke="#fff" strokeWidth={1.6} fill="none" strokeLinecap="round" />
          </svg>
        )}
        {glyph === "cross" && (
          <svg viewBox="0 0 12 12" className="absolute inset-0">
            <path d="M3.5 3.5 L8.5 8.5 M8.5 3.5 L3.5 8.5" stroke="#e06b8b" strokeWidth={1.4} strokeLinecap="round" />
          </svg>
        )}
      </span>
      {label}
    </span>
  );
}
