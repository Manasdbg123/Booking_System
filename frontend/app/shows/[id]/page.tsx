"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useShowSocket, ShowEvent } from "@/lib/useShowSocket";
import { SeatMap, MapSeat, MapSection, SeatState } from "@/components/seat-map";
import { Card, Button, Badge, ErrorState, Skeleton } from "@/components/ui";
import { Countdown } from "@/components/countdown";
import { formatCurrency } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

const MAX_SEATS = 8;

export default function SeatSelectionPage() {
  const { id: showId } = useParams<{ id: string }>();
  const router = useRouter();
  const { token } = useAuth();
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["seatmap", showId], queryFn: () => api.getSeatMap(showId) });

  const [seatOverrides, setSeatOverrides] = useState<Record<string, SeatState>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [holdBooking, setHoldBooking] = useState<any | null>(null);
  const [holdError, setHoldError] = useState<string | null>(null);
  const [holding, setHolding] = useState(false);

  const onSocketEvent = useCallback((evt: ShowEvent) => {
    const seatIds: string[] | undefined = evt.payload?.seat_ids;
    if (!seatIds) return;
    setSeatOverrides((prev) => {
      const next = { ...prev };
      const newState: SeatState = evt.type === "booking.confirmed" ? "SOLD" : evt.type === "booking.held" ? "HELD" : "FREE";
      for (const showSeatId of seatIds) next[showSeatId] = newState;
      return next;
    });
  }, []);
  useShowSocket(showId, onSocketEvent);

  const seats: MapSeat[] = useMemo(() => {
    if (!data) return [];
    return data.seats.map((s: any) => ({
      id: s.id,
      seat_id: s.seat_id,
      row_label: s.row_label,
      seat_number: s.seat_number,
      section_id: s.section_id,
      section_name: s.section_name,
      section_color: s.section_color,
      price: s.price,
      status: seatOverrides[s.id] ?? s.status,
      pos_x: s.pos_x,
      pos_y: s.pos_y,
      is_mine: s.is_mine,
    }));
  }, [data, seatOverrides]);

  const mapSections: MapSection[] = useMemo(
    () => (data?.sections ?? []).map((s: any) => ({ id: s.id, name: s.name, base_price: s.base_price, color: s.color })),
    [data]
  );

  const selectedSeats = seats.filter((s) => selected.has(s.id));
  const total = selectedSeats.reduce((sum, s) => sum + Number(s.price), 0);
  const availableCount = seats.filter((s) => s.status === "FREE").length;

  function toggleSeat(seat: MapSeat) {
    if (holdBooking) return; // locked once a hold is in flight
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(seat.id)) next.delete(seat.id);
      else if (next.size < MAX_SEATS) next.add(seat.id);
      return next;
    });
  }

  async function handleHold() {
    if (!token) {
      router.push("/login");
      return;
    }
    setHolding(true);
    setHoldError(null);
    try {
      const admissionToken = sessionStorage.getItem(`admission_${showId}`) || undefined;
      const booking = await api.createHold(showId, selectedSeats.map((s) => s.seat_id), admissionToken);
      setHoldBooking(booking);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        router.push(`/waiting-room/${showId}`);
        return;
      }
      if (err instanceof ApiError && err.status === 409) {
        setHoldError("Some of your selected seats were just taken. Please re-select.");
        setSelected(new Set());
        refetch();
      } else {
        setHoldError("Couldn't hold these seats. Please try again.");
      }
    } finally {
      setHolding(false);
    }
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-6 h-[420px] w-full rounded-2xl" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12">
        <ErrorState message="Couldn't load the seat map." onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 pb-32 pt-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold sm:text-3xl">Choose your seats</h1>
          <p className="mt-1 text-sm text-white/50">
            Select up to {MAX_SEATS} seats — they&apos;re held for 5 minutes once you confirm.
          </p>
        </div>
        <p className="text-sm tabular-nums text-white/45">
          <span className="font-semibold text-seat-free">{availableCount.toLocaleString()}</span> of{" "}
          {seats.length.toLocaleString()} seats available
        </p>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr,330px]">
        <SeatMap seats={seats} sections={mapSections} selectedIds={selected} onToggle={toggleSeat} maxSelectable={MAX_SEATS} />

        <Card className="h-fit p-5 lg:sticky lg:top-24">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-lg font-medium">Your selection</h2>
            {selectedSeats.length > 0 && (
              <span className="text-xs tabular-nums text-white/40">
                {selectedSeats.length}/{MAX_SEATS}
              </span>
            )}
          </div>

          {selectedSeats.length === 0 ? (
            <div className="mt-4 flex flex-col items-center gap-2 rounded-xl border border-dashed border-border/80 px-4 py-8 text-center">
              <svg viewBox="0 0 24 24" className="h-7 w-7 text-white/20" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="4" y="9" width="16" height="9" rx="2" />
                <path d="M6 9V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2M8 18v2M16 18v2" strokeLinecap="round" />
              </svg>
              <p className="text-sm text-white/45">No seats picked yet</p>
              <p className="text-xs text-white/30">Pick any seat on the map to get started.</p>
            </div>
          ) : (
            <ul className="mt-4 flex flex-col gap-1.5">
              {selectedSeats.map((s) => (
                <li key={s.id} className="flex items-center justify-between rounded-lg bg-white/[0.04] px-3 py-2 text-sm">
                  <span className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.section_color }} />
                    <span className="font-medium">
                      {s.row_label}
                      {s.seat_number}
                    </span>
                    <span className="text-white/40">{s.section_name}</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="tabular-nums text-white/70">{formatCurrency(s.price)}</span>
                    {!holdBooking && (
                      <button
                        aria-label={`Remove seat ${s.row_label}${s.seat_number}`}
                        onClick={() => toggleSeat(s)}
                        className="text-white/30 transition hover:text-red-300"
                      >
                        ✕
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
            <span className="text-sm text-white/60">Total</span>
            <span className="font-display text-xl font-semibold tabular-nums">{formatCurrency(total)}</span>
          </div>

          {holdError && <p className="mt-3 text-sm text-red-400">{holdError}</p>}

          {!holdBooking ? (
            <Button className="mt-5 w-full" disabled={selectedSeats.length === 0 || holding} onClick={handleHold}>
              {holding ? "Holding..." : "Hold selected seats"}
            </Button>
          ) : (
            <div className="mt-5 flex flex-col items-center gap-3 rounded-xl border border-accent/30 bg-accent/5 p-4">
              <Countdown expiresAt={holdBooking.expires_at} onExpire={() => setHoldBooking(null)} size={64} />
              <p className="text-center text-xs text-white/60">Complete checkout before this expires or your seats will be released.</p>
              <Button className="w-full" onClick={() => router.push(`/checkout/${holdBooking.id}`)}>
                Proceed to checkout
              </Button>
            </div>
          )}
        </Card>
      </div>

      {/* Mobile action bar — on a phone the summary card sits below a tall
          seat map, so the total and CTA would otherwise be off-screen. */}
      {selectedSeats.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur lg:hidden">
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs text-white/50">
                {selectedSeats.length} seat{selectedSeats.length > 1 ? "s" : ""} ·{" "}
                {selectedSeats.map((s) => `${s.row_label}${s.seat_number}`).join(", ")}
              </p>
              <p className="font-display text-lg font-semibold leading-tight tabular-nums">{formatCurrency(total)}</p>
            </div>
            {holdBooking ? (
              <div className="flex items-center gap-2">
                <Countdown expiresAt={holdBooking.expires_at} onExpire={() => setHoldBooking(null)} size={40} />
                <Button onClick={() => router.push(`/checkout/${holdBooking.id}`)}>Checkout</Button>
              </div>
            ) : (
              <Button disabled={holding} onClick={handleHold}>
                {holding ? "Holding..." : "Hold seats"}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
