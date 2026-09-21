// Tatkal-style spike load test: many virtual users hit the same show's
// booking flow (join queue if hot -> hold seats -> pay) simultaneously.
//
// Usage (after installing k6: https://k6.io/docs/get-started/installation/):
//   k6 run -e BASE_URL=http://localhost:8000 -e SHOW_ID=<uuid> k6/tatkal-spike.js
//
// Records throughput, p95/p99 latency (k6's built-in http_req_duration
// trend), conflict rate (custom Rate metric on 409s), and double-booking
// count (custom Counter, computed by the companion check-seats.js script
// after the run, since detecting a double-book requires querying Postgres
// directly rather than from the load test client).

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate } from "k6/metrics";

const conflictRate = new Rate("seat_conflicts");
const holdSuccesses = new Counter("hold_successes");
const paySuccesses = new Counter("pay_successes");

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const SHOW_ID = __ENV.SHOW_ID; // required
const SEAT_IDS = __ENV.SEAT_IDS ? __ENV.SEAT_IDS.split(",") : null; // optional: pool of contested seat ids

export const options = {
  scenarios: {
    tatkal_spike: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "10s", target: 200 },
        { duration: "20s", target: 10000 },
        { duration: "30s", target: 10000 },
        { duration: "10s", target: 0 },
      ],
      gracefulRampDown: "10s",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<1500", "p(99)<3000"],
    seat_conflicts: ["rate<1"], // informational, not a hard fail — conflicts are expected under contention
  },
};

function randomEmail() {
  return `loadtest_${__VU}_${__ITER}_${Date.now()}@seatrush.dev`;
}

export default function () {
  if (!SHOW_ID) {
    throw new Error("Set -e SHOW_ID=<uuid> to the show under test");
  }

  const email = randomEmail();
  const registerRes = http.post(
    `${BASE_URL}/api/auth/register`,
    JSON.stringify({ email, password: "LoadTest123!" }),
    { headers: { "Content-Type": "application/json" } }
  );
  if (registerRes.status !== 200) return;
  const token = registerRes.json("access_token");
  const authHeaders = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  // Fetch the current seat map and pick a FREE seat (or use a fixed contested pool).
  const mapRes = http.get(`${BASE_URL}/api/shows/${SHOW_ID}/seatmap`);
  let seatId = null;
  if (SEAT_IDS) {
    seatId = SEAT_IDS[Math.floor(Math.random() * SEAT_IDS.length)];
  } else if (mapRes.status === 200) {
    const free = mapRes.json("seats").filter((s) => s.status === "FREE");
    if (free.length > 0) seatId = free[Math.floor(Math.random() * free.length)].seat_id;
  }
  if (!seatId) return;

  const idempotencyKey = `${__VU}-${__ITER}-${Date.now()}`;
  const holdRes = http.post(
    `${BASE_URL}/api/holds`,
    JSON.stringify({ show_id: SHOW_ID, seat_ids: [seatId] }),
    { headers: { ...authHeaders, "Idempotency-Key": idempotencyKey } }
  );

  conflictRate.add(holdRes.status === 409);
  check(holdRes, { "hold: 201 or 409": (r) => r.status === 201 || r.status === 409 });

  if (holdRes.status === 201) {
    holdSuccesses.add(1);
    const bookingId = holdRes.json("id");
    sleep(Math.random() * 0.5);
    const payRes = http.post(
      `${BASE_URL}/api/bookings/pay`,
      JSON.stringify({ booking_id: bookingId, simulate: "success" }),
      { headers: { ...authHeaders, "Idempotency-Key": `pay-${idempotencyKey}` } }
    );
    if (payRes.status === 200) paySuccesses.add(1);
  }

  sleep(Math.random());
}
