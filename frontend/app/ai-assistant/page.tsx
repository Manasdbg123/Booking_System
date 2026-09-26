"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { api, ApiError } from "@/lib/api";
import { Card, Button, Badge, EmptyState } from "@/components/ui";
import { formatCurrency } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

type ToolCall = { name: string; input: Record<string, any>; outcome: string; result: Record<string, any> };
type ChatTurn = { role: "user" | "assistant"; content: string; toolCalls?: ToolCall[] };

const SUGGESTIONS = [
  "Find me a show under 2000 with seats available",
  "Can I cancel a confirmed booking?",
  "Show me my bookings",
];

export default function AiAssistantPage() {
  const { token, loading: authLoading } = useAuth();
  const router = useRouter();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!authLoading && !token) router.push("/login");
  }, [authLoading, token, router]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, sending]);

  async function send(message: string) {
    if (!message.trim() || sending) return;
    setError(null);
    setTurns((t) => [...t, { role: "user", content: message }]);
    setInput("");
    setSending(true);
    try {
      const res = await api.aiChat(message, sessionId);
      setSessionId(res.session_id);
      setTurns((t) => [...t, { role: "assistant", content: res.reply, toolCalls: res.tool_calls }]);
    } catch (e) {
      const msg = e instanceof ApiError ? String(e.detail) : "The assistant is unavailable right now.";
      setError(msg);
    } finally {
      setSending(false);
    }
  }

  const recommendedEvents = turns
    .flatMap((t) => t.toolCalls ?? [])
    .filter((tc) => tc.name === "search_shows" && tc.outcome === "ok")
    .flatMap((tc) => tc.result.events ?? []);

  const lastBookingAction = turns
    .flatMap((t) => t.toolCalls ?? [])
    .filter((tc) => (tc.name === "create_booking_hold" || tc.name === "confirm_and_pay") && tc.outcome === "ok")
    .at(-1);

  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-4 py-10 lg:grid-cols-[1.4fr_1fr] lg:px-6">
      <Card className="flex h-[75vh] flex-col p-0">
        <div className="border-b border-border px-5 py-4">
          <h1 className="font-display text-lg font-semibold">SeatRush AI Assistant</h1>
          <p className="text-sm text-white/50">Search shows, check policies, and book — with your confirmation at every step.</p>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {turns.length === 0 && (
            <EmptyState
              title="Ask me anything about shows or your bookings"
              description="I can search shows, check seat availability and pricing, answer policy questions, and place holds or cancellations for you — always with your OK first."
            />
          )}
          <AnimatePresence initial={false}>
            {turns.map((turn, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}
              >
                <div
                  className={
                    turn.role === "user"
                      ? "max-w-[80%] rounded-2xl bg-accent px-4 py-2.5 text-sm text-white"
                      : "max-w-[85%] rounded-2xl border border-border bg-surface px-4 py-2.5 text-sm text-white/90"
                  }
                >
                  <p className="whitespace-pre-wrap">{turn.content}</p>
                  {turn.toolCalls && turn.toolCalls.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {turn.toolCalls.map((tc, j) => (
                        <Badge key={j} tone={tc.outcome === "ok" ? "info" : "danger"}>
                          {tc.name}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          {sending && (
            <div className="flex justify-start">
              <div className="rounded-2xl border border-border bg-surface px-4 py-2.5 text-sm text-white/50">Thinking…</div>
            </div>
          )}
          {error && <p className="text-sm text-red-300">{error}</p>}
        </div>

        <div className="border-t border-border p-4">
          {turns.length === 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-border px-3 py-1.5 text-xs text-white/60 transition hover:bg-white/5 hover:text-white"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex gap-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about shows, seats, or your bookings…"
              className="flex-1 rounded-xl border border-border bg-surface px-4 py-2.5 text-sm text-white placeholder:text-white/30 focus:border-accent focus:outline-none"
            />
            <Button type="submit" disabled={sending || !input.trim()}>
              Send
            </Button>
          </form>
        </div>
      </Card>

      <div className="flex flex-col gap-4">
        {lastBookingAction && (
          <Card className="p-5">
            <p className="text-sm font-medium text-white/80">Latest booking action</p>
            <p className="mt-1 text-xs text-white/50">{lastBookingAction.name}</p>
            <p className="mt-2 text-sm">
              Status: <Badge tone="success">{lastBookingAction.result.status}</Badge>
            </p>
            {lastBookingAction.result.booking_id && (
              <Link href={`/checkout/${lastBookingAction.result.booking_id}`} className="mt-3 block">
                <Button className="w-full">Go to booking</Button>
              </Link>
            )}
          </Card>
        )}

        <Card className="p-5">
          <p className="mb-3 text-sm font-medium text-white/80">Recommended shows</p>
          {recommendedEvents.length === 0 ? (
            <p className="text-sm text-white/40">Ask the assistant to find shows and they&apos;ll appear here.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {recommendedEvents.slice(0, 6).map((e: any) => (
                <Link key={e.event_id} href={`/events/${e.event_id}`} className="block rounded-xl border border-border p-3 transition hover:bg-white/5">
                  <p className="font-medium">{e.title}</p>
                  <p className="mt-0.5 text-xs text-white/50">{e.venue}</p>
                  <div className="mt-2 flex items-center justify-between text-xs">
                    <span className="text-white/60">{e.seats_available} seats left</span>
                    {e.from_price && <span className="font-medium text-accent">{formatCurrency(e.from_price)}+</span>}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
