"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { api } from "@/lib/api";
import { Card, Button, ErrorState, Skeleton } from "@/components/ui";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function TicketPage() {
  const { bookingId } = useParams<{ bookingId: string }>();
  const { data: booking, isLoading, isError, refetch } = useQuery({ queryKey: ["booking", bookingId], queryFn: () => api.getBooking(bookingId) });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <Skeleton className="h-96 w-full rounded-2xl" />
      </div>
    );
  }
  if (isError || !booking) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <ErrorState message="Couldn't load this ticket." onRetry={() => refetch()} />
      </div>
    );
  }
  if (booking.status !== "CONFIRMED") {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center text-white/60">
        This booking isn&apos;t confirmed yet (status: {booking.status}).
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-4 py-16" id="ticket-card">
      <Card className="overflow-hidden p-0">
        <div className="bg-gradient-to-br from-accent/30 to-surface2 p-6 text-center">
          <p className="text-xs uppercase tracking-widest text-white/50">SeatRush E-Ticket</p>
          <p className="mt-1 font-display text-xl font-semibold">{booking.ticket_code}</p>
        </div>
        <div className="flex flex-col items-center gap-4 p-6">
          <div className="rounded-2xl bg-white p-4">
            <QRCodeSVG value={JSON.stringify({ booking_id: booking.id, ticket_code: booking.ticket_code })} size={160} />
          </div>
          <ul className="w-full text-sm">
            {booking.seats.map((s: any) => (
              <li key={s.show_seat_id} className="flex justify-between border-b border-border/50 py-2">
                <span>
                  {s.row_label}
                  {s.seat_number} · {s.section_name}
                </span>
                <span className="text-white/60">{formatCurrency(s.price)}</span>
              </li>
            ))}
          </ul>
          <div className="flex w-full justify-between text-sm text-white/60">
            <span>Booked</span>
            <span>{formatDate(booking.created_at)}</span>
          </div>
          <Button className="w-full" onClick={() => window.print()}>
            Download / Print ticket
          </Button>
        </div>
      </Card>
    </div>
  );
}
