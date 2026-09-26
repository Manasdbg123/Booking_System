const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("seatrush_token");
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { idempotencyKey?: string; admissionToken?: string } = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
  if (options.admissionToken) headers["X-Admission-Token"] = options.admissionToken;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      /* no body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function newIdempotencyKey(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export const api = {
  register: (email: string, password: string) =>
    apiFetch<{ access_token: string; role: string }>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; role: string }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  listEvents: () => apiFetch<any[]>("/api/events"),
  getEvent: (id: string) => apiFetch<any>(`/api/events/${id}`),
  getSeatMap: (showId: string) => apiFetch<any>(`/api/shows/${showId}/seatmap`),
  createHold: (showId: string, seatIds: string[], admissionToken?: string) =>
    apiFetch<any>("/api/holds", {
      method: "POST",
      body: JSON.stringify({ show_id: showId, seat_ids: seatIds }),
      idempotencyKey: newIdempotencyKey(),
      admissionToken,
    }),
  pay: (bookingId: string, simulate = "random") =>
    apiFetch<any>("/api/bookings/pay", {
      method: "POST",
      body: JSON.stringify({ booking_id: bookingId, simulate }),
      idempotencyKey: newIdempotencyKey(),
    }),
  cancelBooking: (bookingId: string) =>
    apiFetch<any>("/api/bookings/cancel", { method: "POST", body: JSON.stringify({ booking_id: bookingId }) }),
  getBooking: (id: string) => apiFetch<any>(`/api/bookings/${id}`),
  myBookings: () => apiFetch<any[]>("/api/bookings"),
  joinWaitlist: (showId: string, sectionId: string) =>
    apiFetch<any>("/api/waitlist/join", { method: "POST", body: JSON.stringify({ show_id: showId, section_id: sectionId }) }),
  myWaitlist: () => apiFetch<any[]>("/api/waitlist/mine"),
  joinQueue: (showId: string) => apiFetch<any>("/api/queue/join", { method: "POST", body: JSON.stringify({ show_id: showId }) }),
  queueStatus: (ticketId: string) => apiFetch<any>(`/api/queue/status/${ticketId}`),
  adminMetrics: () => apiFetch<any>("/api/admin/metrics"),
  adminHeatmap: (showId: string) => apiFetch<any>(`/api/admin/shows/${showId}/heatmap`),
  adminAuditLog: () => apiFetch<any[]>("/api/admin/audit-log"),
  adminRecentBookings: () => apiFetch<any[]>("/api/admin/bookings/recent"),
  adminAnalytics: () => apiFetch<any>("/api/admin/analytics"),
  adminAiActivity: () => apiFetch<any[]>("/api/admin/ai-activity"),
  aiChat: (message: string, sessionId?: string) =>
    apiFetch<any>("/api/ai/chat", { method: "POST", body: JSON.stringify({ message, session_id: sessionId ?? null }) }),
  aiSessions: () => apiFetch<any[]>("/api/ai/sessions"),
  aiSessionMessages: (sessionId: string) => apiFetch<any[]>(`/api/ai/sessions/${sessionId}/messages`),
};
