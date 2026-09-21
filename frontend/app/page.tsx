"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { EventPoster } from "@/components/event-poster";
import { formatCurrency } from "@/lib/utils";

function formatShowDate(iso: string | null) {
  if (!iso) return "Dates coming soon";
  return new Date(iso).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
}

export default function HomePage() {
  const { data: events, isLoading, isError, refetch } = useQuery({ queryKey: ["events"], queryFn: api.listEvents });
  const featured = events?.[0];
  const rest = events?.slice(1) ?? [];

  return (
    <div className="mx-auto max-w-7xl px-4 pb-24 sm:px-6">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-3xl border border-border">
        <div className="pointer-events-none absolute -left-24 -top-32 h-80 w-80 rounded-full bg-accent/25 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-40 right-0 h-96 w-96 rounded-full bg-fuchsia-600/15 blur-3xl" />

        <div className="relative grid items-center gap-8 p-8 sm:p-12 lg:grid-cols-[1.1fr,0.9fr] lg:p-16">
          <div>
            <motion.span
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-medium text-accent-glow"
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-glow opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent-glow" />
              </span>
              Live seat availability
            </motion.span>

            <motion.h1
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.05 }}
              className="mt-5 font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl"
            >
              Shows worth
              <br />
              <span className="text-gradient">fighting for.</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.12 }}
              className="mt-5 max-w-lg text-base leading-relaxed text-white/55"
            >
              Real-time seat maps, fair queues when demand spikes, and a booking engine that will never sell the same
              seat twice.
            </motion.p>

            {featured && (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.2 }}
                className="mt-8 flex flex-wrap items-center gap-3"
              >
                <Link
                  href={`/events/${featured.id}`}
                  className="inline-flex items-center gap-2 rounded-xl bg-accent px-6 py-3 font-medium text-white shadow-glow transition hover:bg-accent-soft"
                >
                  Book {featured.title.split(/[—:]/)[0].trim()}
                  <span aria-hidden>→</span>
                </Link>
                <span className="text-sm text-white/40">
                  {events?.length} events · {events?.reduce((n, e) => n + (e.seats_available ?? 0), 0).toLocaleString()} seats live
                </span>
              </motion.div>
            )}
          </div>

          {featured && (
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.6, delay: 0.15 }}
              className="hidden lg:block"
            >
              <Link href={`/events/${featured.id}`}>
                <Card className="group overflow-hidden p-0 transition hover:shadow-glow">
                  <div className="relative h-60">
                    <EventPoster title={featured.title} className="absolute inset-0" tall />
                    <div className="absolute inset-0 bg-gradient-to-t from-surface via-surface/20 to-transparent" />
                    {featured.is_hot && (
                      <span className="absolute right-3 top-3">
                        <Badge tone="warning">🔥 High demand</Badge>
                      </span>
                    )}
                  </div>
                  <div className="p-5">
                    <p className="text-xs uppercase tracking-widest text-accent-glow">Featured</p>
                    <h2 className="mt-1 font-display text-xl font-semibold">{featured.title}</h2>
                    <div className="mt-3 flex items-center justify-between text-sm">
                      <span className="text-white/50">{formatShowDate(featured.next_show_at)} · {featured.venue?.name}</span>
                      {featured.from_price && (
                        <span className="font-medium text-white">from {formatCurrency(featured.from_price)}</span>
                      )}
                    </div>
                  </div>
                </Card>
              </Link>
            </motion.div>
          )}
        </div>
      </section>

      {/* Grid */}
      <section className="mt-16">
        <div className="mb-6 flex items-baseline justify-between">
          <h2 className="font-display text-2xl font-semibold">What&apos;s on</h2>
          {events && <span className="text-sm text-white/35">{events.length} events</span>}
        </div>

        {isError && <ErrorState message="Couldn't load events. Is the API running on port 8000?" onRetry={() => refetch()} />}

        {isLoading && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Card key={i} className="overflow-hidden p-0">
                <Skeleton className="h-40 rounded-none" />
                <div className="space-y-3 p-5">
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-1/3" />
                </div>
              </Card>
            ))}
          </div>
        )}

        {!isLoading && !isError && events?.length === 0 && (
          <EmptyState title="No events yet" description="Run the seed script to load the demo dataset." />
        )}

        {!isLoading && events && events.length > 0 && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {rest.map((event, i) => {
              const soldOut = event.seats_available === 0;
              return (
                <motion.div
                  key={event.id}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.05, 0.3) }}
                >
                  <Link href={`/events/${event.id}`} className="block h-full">
                    <Card className="group flex h-full flex-col overflow-hidden p-0 transition duration-300 hover:-translate-y-1 hover:shadow-glow">
                      <div className="relative h-40 overflow-hidden">
                        <EventPoster title={event.title} className="absolute inset-0 transition duration-500 group-hover:scale-105" />
                        <div className="absolute inset-0 bg-gradient-to-t from-surface/95 via-surface/25 to-transparent" />
                        <div className="absolute left-3 top-3 flex gap-2">
                          {event.is_hot && <Badge tone="warning">High demand</Badge>}
                          {soldOut && <Badge tone="danger">Sold out</Badge>}
                        </div>
                        <p className="absolute bottom-3 left-4 text-xs font-medium text-white/80">
                          {formatShowDate(event.next_show_at)}
                        </p>
                      </div>

                      <div className="flex flex-1 flex-col p-5">
                        <h3 className="font-display text-lg font-medium leading-snug text-white transition group-hover:text-accent-glow">
                          {event.title}
                        </h3>
                        <p className="mt-1.5 line-clamp-2 text-sm text-white/45">{event.description}</p>

                        <div className="mt-auto flex items-end justify-between pt-4">
                          <div>
                            <p className="text-xs text-white/35">{event.venue?.name}</p>
                            <p className="mt-0.5 text-xs text-white/30">
                              {event.seats_available?.toLocaleString()} of {event.seats_total?.toLocaleString()} seats left
                            </p>
                          </div>
                          {event.from_price && (
                            <p className="text-right">
                              <span className="block text-[10px] uppercase tracking-wide text-white/30">from</span>
                              <span className="font-display text-lg font-semibold text-white">
                                {formatCurrency(event.from_price)}
                              </span>
                            </p>
                          )}
                        </div>
                      </div>
                    </Card>
                  </Link>
                </motion.div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
