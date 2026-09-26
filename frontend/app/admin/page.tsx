"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { Card, Badge, Skeleton, ErrorState } from "@/components/ui";
import { formatCurrency, formatDate } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

const BOOKING_TONE: Record<string, "default" | "success" | "warning" | "danger" | "info"> = {
  CONFIRMED: "success",
  HELD: "warning",
  PAYMENT_PENDING: "info",
  FAILED: "danger",
  EXPIRED: "default",
  CANCELLED: "default",
};

const SEAT_STATE_STYLE: Record<string, { label: string; color: string }> = {
  FREE: { label: "Available", color: "#2dd4bf" },
  HELD: { label: "Held", color: "#f59e0b" },
  SOLD: { label: "Sold", color: "#8b5cf6" },
};

function SeatHeatmap({ showId }: { showId: string | undefined }) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-heatmap", showId],
    queryFn: () => api.adminHeatmap(showId!),
    enabled: !!showId,
    refetchInterval: 5000,
  });

  if (!showId) return <p className="text-sm text-white/40">Pick a show to see its seat breakdown.</p>;
  if (isLoading || !data) return <Skeleton className="h-24 w-full" />;

  const order = ["SOLD", "HELD", "FREE"];
  const total = order.reduce((n, k) => n + (data[k] ?? 0), 0) || 1;

  return (
    <div>
      <div className="flex h-4 w-full overflow-hidden rounded-full border border-border">
        {order.map((key) => {
          const value = data[key] ?? 0;
          if (!value) return null;
          return (
            <div
              key={key}
              title={`${SEAT_STATE_STYLE[key].label}: ${value}`}
              style={{ width: `${(value / total) * 100}%`, background: SEAT_STATE_STYLE[key].color }}
            />
          );
        })}
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3">
        {order.map((key) => {
          const value = data[key] ?? 0;
          return (
            <div key={key} className="rounded-xl border border-border bg-surface2/50 p-3">
              <span className="flex items-center gap-1.5 text-xs text-white/50">
                <span className="h-2 w-2 rounded-full" style={{ background: SEAT_STATE_STYLE[key].color }} />
                {SEAT_STATE_STYLE[key].label}
              </span>
              <p className="mt-1 font-display text-xl font-semibold tabular-nums">{value.toLocaleString()}</p>
              <p className="text-[11px] text-white/30">{((value / total) * 100).toFixed(1)}%</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const { role, token, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && (!token || role !== "ADMIN")) router.push("/");
  }, [loading, token, role, router]);

  const { data: metrics, isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-metrics"],
    queryFn: api.adminMetrics,
    refetchInterval: 5000,
    enabled: role === "ADMIN",
  });
  const { data: auditLog } = useQuery({ queryKey: ["admin-audit"], queryFn: api.adminAuditLog, refetchInterval: 8000, enabled: role === "ADMIN" });
  const { data: analytics } = useQuery({ queryKey: ["admin-analytics"], queryFn: api.adminAnalytics, refetchInterval: 8000, enabled: role === "ADMIN" });
  const { data: aiActivity } = useQuery({ queryKey: ["admin-ai-activity"], queryFn: api.adminAiActivity, refetchInterval: 8000, enabled: role === "ADMIN" });
  const { data: recentBookings } = useQuery({
    queryKey: ["admin-recent-bookings"],
    queryFn: api.adminRecentBookings,
    refetchInterval: 5000,
    enabled: role === "ADMIN",
  });
  const { data: events } = useQuery({ queryKey: ["events"], queryFn: api.listEvents, enabled: role === "ADMIN" });

  const [selectedShow, setSelectedShow] = useState<string | undefined>();
  const activeShow = selectedShow ?? events?.[0]?.next_show_id;

  if (role !== "ADMIN") return null;

  return (
    <div className="mx-auto max-w-6xl px-4 py-16">
      <h1 className="font-display text-2xl font-semibold">Admin dashboard</h1>

      {isError && <ErrorState message="Couldn't load metrics." onRetry={() => refetch()} />}
      {isLoading ? (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-2xl" />
          ))}
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MetricCard label="Active holds" value={metrics?.active_holds} />
          <MetricCard label="Sales (last hour)" value={metrics?.sales_last_hour} />
          <MetricCard label="Queue depth" value={metrics?.queue_depth} />
          <MetricCard label="Outbox backlog" value={metrics?.outbox_backlog} />
        </div>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricCard label="Total users" value={analytics?.total_users} />
        <MetricCard label="Revenue" value={analytics ? Number(analytics.revenue) : undefined} format={formatCurrency} />
        <MetricCard label="Cancellation rate" value={analytics?.cancellation_rate_pct} format={(v) => `${v}%`} />
        <MetricCard label="Failed payments" value={analytics?.failed_payments} />
      </div>

      {/* Per-show seat heatmap */}
      <div className="mb-4 mt-12 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold">Seat heatmap</h2>
        <select
          aria-label="Select show"
          value={activeShow ?? ""}
          onChange={(e) => setSelectedShow(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-white/80 focus:border-accent focus:outline-none"
        >
          {events?.map((e: any) => (
            <option key={e.id} value={e.next_show_id ?? ""}>
              {e.title}
            </option>
          ))}
        </select>
      </div>
      <Card className="p-5">
        <SeatHeatmap showId={activeShow} />
      </Card>

      <h2 className="mb-4 mt-12 font-display text-lg font-semibold">Recent bookings</h2>
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border text-white/50">
            <tr>
              <th className="px-4 py-3">Booking</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Updated</th>
            </tr>
          </thead>
          <tbody>
            {recentBookings?.map((b: any) => (
              <tr key={b.id} className="border-b border-border/50">
                <td className="px-4 py-3 font-mono text-xs">{b.id.slice(0, 8)}</td>
                <td className="px-4 py-3">
                  <Badge tone={BOOKING_TONE[b.status] ?? "default"}>{b.status}</Badge>
                </td>
                <td className="px-4 py-3 tabular-nums">{formatCurrency(b.total_amount)}</td>
                <td className="px-4 py-3 text-white/50">{formatDate(b.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <h2 className="mb-4 mt-12 font-display text-lg font-semibold">Audit log</h2>
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border text-white/50">
            <tr>
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Entity</th>
              <th className="px-4 py-3">Outcome</th>
              <th className="px-4 py-3">When</th>
            </tr>
          </thead>
          <tbody>
            {auditLog?.length ? (
              auditLog.map((a: any) => (
                <tr key={a.id} className="border-b border-border/50">
                  <td className="px-4 py-3">{a.actor}</td>
                  <td className="px-4 py-3">{a.action}</td>
                  <td className="px-4 py-3">
                    {a.entity} <span className="text-white/40">#{a.entity_id.slice(0, 8)}</span>
                  </td>
                  <td className="px-4 py-3">{a.outcome}</td>
                  <td className="px-4 py-3 text-white/50">{formatDate(a.created_at)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-white/40">
                  No audit log entries yet — these are written by the optional ops agent when enabled.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
      <h2 className="mb-4 mt-12 font-display text-lg font-semibold">AI activity log</h2>
      <p className="mb-3 text-sm text-white/50">Every irreversible action (and every failed tool call) the AI booking assistant has taken, across all users.</p>
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border text-white/50">
            <tr>
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Tool</th>
              <th className="px-4 py-3">Outcome</th>
              <th className="px-4 py-3">When</th>
            </tr>
          </thead>
          <tbody>
            {aiActivity?.length ? (
              aiActivity.map((a: any) => (
                <tr key={a.id} className="border-b border-border/50">
                  <td className="px-4 py-3 font-mono text-xs">{a.actor.replace("ai_agent:", "").slice(0, 8)}</td>
                  <td className="px-4 py-3">{a.action.replace("tool_call:", "")}</td>
                  <td className="px-4 py-3">
                    <Badge tone={a.outcome === "ok" ? "success" : "danger"}>{a.outcome}</Badge>
                  </td>
                  <td className="px-4 py-3 text-white/50">{formatDate(a.created_at)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-white/40">
                  No AI-initiated actions yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function MetricCard({ label, value, format }: { label: string; value: number | undefined; format?: (v: number) => string }) {
  return (
    <Card className="p-5">
      <p className="text-xs uppercase tracking-wide text-white/40">{label}</p>
      <p className="mt-2 font-display text-3xl font-semibold">{value === undefined ? "–" : format ? format(value) : value}</p>
    </Card>
  );
}
