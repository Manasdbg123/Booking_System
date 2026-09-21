"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, Badge, ErrorState, Skeleton } from "@/components/ui";
import { formatDate } from "@/lib/utils";

export default function EventPage() {
  const { id } = useParams<{ id: string }>();
  const { data: event, isLoading, isError, refetch } = useQuery({ queryKey: ["event", id], queryFn: () => api.getEvent(id) });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="mt-4 h-24 w-full" />
      </div>
    );
  }
  if (isError || !event) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16">
        <ErrorState message="Couldn't load this event." onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-16">
      <p className="text-sm text-accent-glow">{event.venue?.name}</p>
      <h1 className="mt-2 font-display text-4xl font-semibold">{event.title}</h1>
      <p className="mt-4 max-w-2xl text-white/60">{event.description}</p>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {event.shows?.map((show: any) => (
          <Link key={show.id} href={`/shows/${show.id}`}>
            <Card className="p-5 transition hover:-translate-y-1 hover:shadow-glow">
              <div className="flex items-center justify-between">
                <p className="font-medium text-white">{formatDate(show.starts_at)}</p>
                {show.is_hot && <Badge tone="warning">High demand</Badge>}
              </div>
              <p className="mt-2 text-sm text-white/50">Tap to view the seat map</p>
            </Card>
          </Link>
        ))}
        {!event.shows?.length && <p className="text-white/50">No showtimes scheduled yet.</p>}
      </div>
    </div>
  );
}
