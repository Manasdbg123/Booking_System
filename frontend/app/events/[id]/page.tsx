"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Badge, Card, ErrorState, Skeleton } from "@/components/ui";
import { EventPoster } from "@/components/event-poster";
import { formatCurrency } from "@/lib/utils";

export default function EventPage() {
  const { id } = useParams<{ id: string }>();
  const { data: event, isLoading, isError, refetch } = useQuery({ queryKey: ["event", id], queryFn: () => api.getEvent(id) });

  const firstShowId = event?.shows?.[0]?.id;
  const { data: seatMap } = useQuery({
    queryKey: ["seatmap-preview", firstShowId],
    queryFn: () => api.getSeatMap(firstShowId!),
    enabled: !!firstShowId,
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12">
        <Skeleton className="h-64 w-full rounded-3xl" />
        <Skeleton className="mt-8 h-8 w-1/3" />
        <Skeleton className="mt-4 h-24 w-full" />
      </div>
    );
  }
  if (isError || !event) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16">
        <ErrorState message="Couldn't load this event." onRetry={() => refetch()} />
      </div>
    );
  }

  const sections = seatMap?.sections ?? [];

  return (
    <div className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
      {/* Hero banner */}
      <section className="relative mt-6 overflow-hidden rounded-3xl border border-border">
        <EventPoster title={event.title} className="absolute inset-0 opacity-45" tall />
        <div className="absolute inset-0 bg-gradient-to-t from-bg via-bg/80 to-transparent" />
        <div className="relative flex flex-col justify-end gap-3 p-8 pt-40 sm:p-12 sm:pt-56">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="info">{event.venue?.name}</Badge>
            {event.shows?.some((s: any) => s.is_hot) && <Badge tone="warning">High demand — waiting room active</Badge>}
          </div>
          <h1 className="font-display text-3xl font-semibold leading-tight sm:text-5xl">{event.title}</h1>
          <p className="max-w-2xl text-white/55">{event.description}</p>
          <p className="text-sm text-white/35">{event.venue?.address}</p>
        </div>
      </section>

      <div className="mt-10 grid gap-8 lg:grid-cols-[1.4fr,1fr]">
        {/* Showtimes */}
        <section>
          <h2 className="mb-4 font-display text-xl font-semibold">Showtimes</h2>
          <div className="flex flex-col gap-3">
            {event.shows?.map((show: any) => {
              const date = new Date(show.starts_at);
              return (
                <Link key={show.id} href={`/shows/${show.id}`}>
                  <Card className="group flex items-center gap-5 p-4 transition hover:-translate-y-0.5 hover:shadow-glow">
                    <div className="flex h-16 w-16 shrink-0 flex-col items-center justify-center rounded-xl border border-border bg-surface2">
                      <span className="text-[10px] uppercase tracking-wide text-white/40">
                        {date.toLocaleDateString("en-IN", { month: "short" })}
                      </span>
                      <span className="font-display text-xl font-semibold leading-none">{date.getDate()}</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-white">
                        {date.toLocaleDateString("en-IN", { weekday: "long" })},{" "}
                        {date.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}
                      </p>
                      <p className="mt-0.5 text-sm text-white/40">{event.venue?.name}</p>
                    </div>
                    {show.is_hot && <Badge tone="warning">Hot</Badge>}
                    <span className="text-white/30 transition group-hover:translate-x-0.5 group-hover:text-accent-glow" aria-hidden>
                      →
                    </span>
                  </Card>
                </Link>
              );
            })}
            {!event.shows?.length && <p className="text-white/45">No showtimes scheduled yet.</p>}
          </div>
        </section>

        {/* Price legend */}
        <section>
          <h2 className="mb-4 font-display text-xl font-semibold">Ticket prices</h2>
          <Card className="p-5">
            {sections.length === 0 ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : (
              <ul className="flex flex-col gap-3">
                {[...sections]
                  .sort((a: any, b: any) => Number(b.base_price) - Number(a.base_price))
                  .map((s: any) => (
                    <li key={s.id} className="flex items-center justify-between">
                      <span className="flex items-center gap-2.5">
                        <span className="h-3.5 w-3.5 rounded-[4px] border-2" style={{ borderColor: s.color, background: `${s.color}22` }} />
                        <span className="text-sm text-white/80">{s.name}</span>
                      </span>
                      <span className="font-display font-semibold tabular-nums">{formatCurrency(s.base_price)}</span>
                    </li>
                  ))}
              </ul>
            )}
            <p className="mt-5 border-t border-border pt-4 text-xs leading-relaxed text-white/35">
              Seats closest to the stage are Platinum; prices step down toward the back of the hall. Your seats are held
              for 5 minutes once selected.
            </p>
          </Card>
        </section>
      </div>
    </div>
  );
}
