# Benchmarks

**Status: not yet run.** This environment has no Docker and no running
Postgres/Redis instance, so the k6 load test (`k6/tatkal-spike.js`) has not
been executed, and the numbers below are placeholders showing the format to
fill in — not real measurements. Do not treat anything in this file as a
verified result until you've actually run it.

## How to run it

1. Get the stack running locally (see `docs/local-setup.md`).
2. Seed data and grab a show id with a decent seat count:
   ```sql
   SELECT id, title FROM events JOIN shows ON shows.event_id = events.id;
   ```
3. Mark that show "hot" to exercise the waiting room too (optional):
   ```
   POST /api/admin/shows/{show_id}/mark-hot   (as the admin user)
   ```
4. Install k6: https://k6.io/docs/get-started/installation/
5. Run:
   ```
   k6 run -e BASE_URL=http://localhost:8000 -e SHOW_ID=<uuid> k6/tatkal-spike.js
   ```
6. After the run, verify zero double-bookings directly against Postgres:
   ```
   psql -U seatrush -d seatrush -f k6/check-double-bookings.sql
   ```

## Results template

| Metric | Value |
|---|---|
| Hardware | *(CPU, RAM, OS)* |
| Postgres version / config | *(e.g. postgres:16, default config)* |
| Peak virtual users | *(from `options.scenarios` in the script, default 10,000)* |
| Total requests | |
| Throughput (req/s, peak) | |
| p50 latency | |
| p95 latency | |
| p99 latency | |
| Hold conflict rate (409s / total holds) | |
| Double-booking count | **must be 0** |
| Errors (5xx) | |

Fill this table in from your own run and keep the raw k6 JSON summary
(`k6 run --summary-export=docs/benchmarks-raw.json ...`) alongside it for
anyone who wants to double check the numbers.
