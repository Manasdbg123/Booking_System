"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, Badge, Skeleton, ErrorState } from "@/components/ui";
import { formatDate } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

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
  const { data: recentBookings } = useQuery({
    queryKey: ["admin-recent-bookings"],
    queryFn: api.adminRecentBookings,
    refetchInterval: 5000,
    enabled: role === "ADMIN",
  });

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
                  <Badge>{b.status}</Badge>
                </td>
                <td className="px-4 py-3">{b.total_amount}</td>
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
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <Card className="p-5">
      <p className="text-xs uppercase tracking-wide text-white/40">{label}</p>
      <p className="mt-2 font-display text-3xl font-semibold">{value ?? "–"}</p>
    </Card>
  );
}
