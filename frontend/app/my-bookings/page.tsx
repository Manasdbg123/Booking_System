"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { Card, Badge, Button, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { formatCurrency, formatDate } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

const STATUS_TONE: Record<string, "default" | "success" | "warning" | "danger" | "info"> = {
  HELD: "warning",
  PAYMENT_PENDING: "info",
  CONFIRMED: "success",
  FAILED: "danger",
  EXPIRED: "default",
  CANCELLED: "default",
};

export default function MyBookingsPage() {
  const { token, loading: authLoading } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const { data: bookings, isLoading, isError, refetch } = useQuery({ queryKey: ["my-bookings"], queryFn: api.myBookings, enabled: !!token });
  const { data: waitlist } = useQuery({ queryKey: ["my-waitlist"], queryFn: api.myWaitlist, enabled: !!token });

  useEffect(() => {
    if (!authLoading && !token) router.push("/login");
  }, [authLoading, token, router]);

  async function cancel(id: string) {
    await api.cancelBooking(id);
    qc.invalidateQueries({ queryKey: ["my-bookings"] });
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-16">
      <h1 className="font-display text-2xl font-semibold">My bookings</h1>

      {isLoading && (
        <div className="mt-6 flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-2xl" />
          ))}
        </div>
      )}
      {isError && <ErrorState message="Couldn't load your bookings." onRetry={() => refetch()} />}
      {!isLoading && bookings?.length === 0 && (
        <div className="mt-6">
          <EmptyState title="No bookings yet" description="Browse events and hold your first seats." action={<Link href="/"><Button>Browse events</Button></Link>} />
        </div>
      )}

      <div className="mt-6 flex flex-col gap-3">
        {bookings?.map((b: any) => (
          <Card key={b.id} className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <p className="font-medium">{b.seats.length} seat{b.seats.length > 1 ? "s" : ""}</p>
                <Badge tone={STATUS_TONE[b.status] ?? "default"}>{b.status}</Badge>
              </div>
              <p className="mt-1 text-sm text-white/50">
                {formatCurrency(b.total_amount)} · Booked {formatDate(b.created_at)}
              </p>
            </div>
            <div className="flex gap-2">
              {b.status === "CONFIRMED" && (
                <Link href={`/tickets/${b.id}`}>
                  <Button variant="ghost">View ticket</Button>
                </Link>
              )}
              {b.status === "HELD" && (
                <Link href={`/checkout/${b.id}`}>
                  <Button>Complete payment</Button>
                </Link>
              )}
              {(b.status === "HELD" || b.status === "CONFIRMED") && (
                <Button variant="danger" onClick={() => cancel(b.id)}>
                  Cancel
                </Button>
              )}
            </div>
          </Card>
        ))}
      </div>

      {waitlist && waitlist.length > 0 && (
        <>
          <h2 className="mb-4 mt-12 font-display text-xl font-semibold">Waitlist</h2>
          <div className="flex flex-col gap-3">
            {waitlist.map((w: any) => (
              <Card key={w.id} className="flex items-center justify-between p-4">
                <p className="text-sm">Position #{w.position}</p>
                <Badge tone={w.status === "OFFERED" ? "success" : "default"}>{w.status}</Badge>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
