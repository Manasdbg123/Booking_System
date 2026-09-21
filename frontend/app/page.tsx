"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { Card, EmptyState, ErrorState, Skeleton } from "@/components/ui";

export default function HomePage() {
  const { data: events, isLoading, isError, refetch } = useQuery({ queryKey: ["events"], queryFn: api.listEvents });
  const featured = events?.[0];

  return (
    <div className="mx-auto max-w-7xl px-4 pb-24 sm:px-6">
      <section className="relative overflow-hidden rounded-3xl border border-border py-20 text-center sm:py-28">
        <div className="absolute inset-0 -z-10 bg-grid-fade" />
        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="font-display text-4xl font-semibold leading-tight sm:text-6xl"
        >
          Shows worth <span className="text-gradient">fighting</span> for.
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="mx-auto mt-4 max-w-xl text-white/60"
        >
          Real-time seat maps, fair queues under high demand, and zero double-bookings — guaranteed.
        </motion.p>
        {featured && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }} className="mt-8">
            <Link
              href={`/events/${featured.id}`}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-6 py-3 font-medium text-white shadow-glow transition hover:bg-accent-soft"
            >
              Explore {featured.title}
            </Link>
          </motion.div>
        )}
      </section>

      <section className="mt-16">
        <h2 className="mb-6 font-display text-2xl font-semibold">All events</h2>
        {isError && <ErrorState message="Couldn't load events. Is the API running?" onRetry={() => refetch()} />}
        {isLoading && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-56 rounded-2xl" />
            ))}
          </div>
        )}
        {!isLoading && !isError && events?.length === 0 && (
          <EmptyState title="No events yet" description="Run the seed script to load demo data." />
        )}
        {!isLoading && events && events.length > 0 && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {events.map((event, i) => (
              <motion.div key={event.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                <Link href={`/events/${event.id}`}>
                  <Card className="group h-full overflow-hidden p-5 transition hover:-translate-y-1 hover:shadow-glow">
                    <div className="mb-4 flex h-32 items-center justify-center rounded-xl bg-gradient-to-br from-accent/30 to-surface2 text-4xl">
                      🎟️
                    </div>
                    <h3 className="font-display text-lg font-medium text-white group-hover:text-accent-glow">{event.title}</h3>
                    <p className="mt-1 line-clamp-2 text-sm text-white/50">{event.description}</p>
                    <p className="mt-3 text-xs text-white/40">{event.venue?.name}</p>
                  </Card>
                </Link>
              </motion.div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
