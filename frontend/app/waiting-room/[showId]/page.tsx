"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { Card } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function WaitingRoomPage() {
  const { showId } = useParams<{ showId: string }>();
  const router = useRouter();
  const { token, loading: authLoading } = useAuth();
  const [status, setStatus] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ticketIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!token) {
      router.push("/login");
      return;
    }

    let cancelled = false;
    let interval: ReturnType<typeof setInterval>;

    async function start() {
      try {
        const joined = await api.joinQueue(showId);
        if (cancelled) return;
        ticketIdRef.current = joined.ticket_id;
        setStatus(joined);
        if (joined.status === "ADMITTED") {
          admitAndRedirect(joined);
          return;
        }
        interval = setInterval(async () => {
          if (!ticketIdRef.current) return;
          const s = await api.queueStatus(ticketIdRef.current);
          if (cancelled) return;
          setStatus(s);
          if (s.status === "ADMITTED") {
            clearInterval(interval);
            admitAndRedirect(s);
          }
        }, 2500);
      } catch (e) {
        setError("Couldn't join the queue. Please try again.");
      }
    }

    function admitAndRedirect(s: any) {
      sessionStorage.setItem(`admission_${showId}`, s.admission_token);
      setTimeout(() => router.push(`/shows/${showId}`), 1200);
    }

    start();
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [showId, token, authLoading, router]);

  return (
    <div className="mx-auto flex max-w-lg flex-col items-center px-4 py-24 text-center">
      <Card className="w-full p-10">
        {error && <p className="text-red-400">{error}</p>}
        {!error && !status && <p className="text-white/60">Joining the queue...</p>}
        {!error && status && status.status !== "ADMITTED" && (
          <>
            <motion.div
              animate={{ scale: [1, 1.05, 1] }}
              transition={{ repeat: Infinity, duration: 2 }}
              className="mx-auto mb-6 flex h-24 w-24 items-center justify-center rounded-full border-4 border-accent/40 font-display text-3xl font-semibold"
            >
              #{status.position}
            </motion.div>
            <h1 className="font-display text-xl font-semibold">You&apos;re in the queue</h1>
            <p className="mt-2 text-white/50">
              Estimated wait: {status.estimated_wait_seconds < 60 ? "under a minute" : `${Math.ceil(status.estimated_wait_seconds / 60)} min`}
            </p>
            <p className="mt-4 text-xs text-white/30">Hang tight — we&apos;ll admit you automatically. Don&apos;t refresh this page.</p>
          </>
        )}
        {!error && status?.status === "ADMITTED" && (
          <>
            <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="mb-4 text-5xl">
              ✅
            </motion.div>
            <h1 className="font-display text-xl font-semibold">You&apos;re in!</h1>
            <p className="mt-2 text-white/50">Redirecting you to seat selection...</p>
          </>
        )}
      </Card>
    </div>
  );
}
