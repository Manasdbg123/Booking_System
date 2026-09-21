"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { Card, Button, ErrorState, Skeleton } from "@/components/ui";
import { Countdown } from "@/components/countdown";
import { formatCurrency } from "@/lib/utils";

type PayState = "idle" | "pending" | "success" | "failure" | "timeout";

export default function CheckoutPage() {
  const { bookingId } = useParams<{ bookingId: string }>();
  const router = useRouter();
  const { data: booking, isLoading, isError, refetch } = useQuery({
    queryKey: ["booking", bookingId],
    queryFn: () => api.getBooking(bookingId),
    refetchInterval: (q) => (["HELD", "PAYMENT_PENDING"].includes(q.state.data?.status) ? 2000 : false),
  });

  const [payState, setPayState] = useState<PayState>("idle");
  const [simulate, setSimulate] = useState("success");

  useEffect(() => {
    if (booking?.status === "CONFIRMED") setPayState("success");
    if (booking?.status === "FAILED") setPayState("failure");
  }, [booking?.status]);

  async function pay() {
    setPayState("pending");
    try {
      await api.pay(bookingId, simulate);
      if (simulate === "timeout") {
        setTimeout(() => setPayState((p) => (p === "pending" ? "timeout" : p)), 6000);
      }
    } catch {
      setPayState("failure");
    }
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }
  if (isError || !booking) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <ErrorState message="Couldn't load this booking." onRetry={() => refetch()} />
      </div>
    );
  }

  if (booking.status === "EXPIRED") {
    return (
      <div className="mx-auto max-w-lg px-4 py-16">
        <Card className="p-8 text-center">
          <p className="text-3xl">⏰</p>
          <h1 className="mt-3 font-display text-xl font-semibold">Your hold expired</h1>
          <p className="mt-2 text-sm text-white/50">Your seats were released back into the pool. You can select new seats or join the waitlist.</p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Button onClick={() => router.push(`/shows/${booking.show_id}`)}>Re-select seats</Button>
            <Button variant="ghost" onClick={() => router.push(`/shows/${booking.show_id}`)}>
              Join waitlist instead
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const seatCount = booking.seats.length;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-72px)] max-w-lg items-center px-4 py-10">
      <Card className="w-full p-8">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-xl font-semibold">Checkout</h1>
            <p className="mt-0.5 text-sm text-white/45">
              {seatCount} seat{seatCount > 1 ? "s" : ""} reserved for you
            </p>
          </div>
          {booking.expires_at && payState === "idle" && (
            <div className="flex flex-col items-center gap-1">
              <Countdown expiresAt={booking.expires_at} onExpire={() => refetch()} />
              <span className="text-[10px] uppercase tracking-wide text-white/35">held</span>
            </div>
          )}
        </div>

        <ul className="mb-4 flex flex-col gap-1.5 text-sm">
          {booking.seats.map((s: any) => (
            <li key={s.show_seat_id} className="flex justify-between rounded-lg bg-white/[0.04] px-3 py-2">
              <span>
                <span className="font-medium">
                  {s.row_label}
                  {s.seat_number}
                </span>
                <span className="ml-2 text-white/40">{s.section_name}</span>
              </span>
              <span className="tabular-nums text-white/70">{formatCurrency(s.price)}</span>
            </li>
          ))}
        </ul>
        <div className="mb-6 flex items-center justify-between border-t border-border pt-4">
          <span className="text-white/60">Total</span>
          <span className="font-display text-2xl font-semibold tabular-nums">{formatCurrency(booking.total_amount)}</span>
        </div>

        {payState === "idle" && (
          <>
            <p className="mb-2 text-xs text-white/40">Demo: simulate a payment outcome</p>
            <div className="mb-4 flex flex-wrap gap-2">
              {["success", "failure", "timeout", "random"].map((opt) => (
                <button
                  key={opt}
                  onClick={() => setSimulate(opt)}
                  className={`rounded-lg border px-3 py-1.5 text-xs capitalize ${simulate === opt ? "border-accent bg-accent/10 text-accent-glow" : "border-border text-white/50"}`}
                >
                  {opt}
                </button>
              ))}
            </div>
            <Button className="w-full" onClick={pay}>
              Pay {formatCurrency(booking.total_amount)}
            </Button>
          </>
        )}

        {payState === "pending" && (
          <div className="flex flex-col items-center gap-3 py-6">
            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }} className="h-10 w-10 rounded-full border-2 border-accent border-t-transparent" />
            <p className="text-sm text-white/60">Processing payment...</p>
          </div>
        )}

        {payState === "success" && (
          <div className="flex flex-col items-center gap-3 py-6">
            <p className="text-4xl">🎉</p>
            <p className="font-medium text-emerald-300">Payment successful!</p>
            <Button onClick={() => router.push(`/tickets/${booking.id}`)}>View your ticket</Button>
          </div>
        )}

        {payState === "failure" && (
          <div className="flex flex-col items-center gap-3 py-6">
            <p className="text-4xl">😔</p>
            <p className="font-medium text-red-300">Payment failed</p>
            <p className="text-center text-xs text-white/50">Your seats have been released. You can try selecting again.</p>
            <Button variant="ghost" onClick={() => router.push(`/shows/${booking.show_id}`)}>
              Back to seat selection
            </Button>
          </div>
        )}

        {payState === "timeout" && (
          <div className="flex flex-col items-center gap-3 py-6">
            <p className="text-4xl">⌛</p>
            <p className="font-medium text-amber-300">Payment is taking longer than expected</p>
            <p className="text-center text-xs text-white/50">We&apos;ll confirm automatically the moment we hear back — check My Bookings shortly.</p>
            <Button variant="ghost" onClick={() => router.push("/my-bookings")}>
              Go to My Bookings
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
