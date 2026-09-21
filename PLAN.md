# SeatRush — Plan

## Environment note
Dev machine has no Docker (too heavy for this hardware) and no Python 3.12 preinstalled (3.14 is). `docker-compose.yml` is included for anyone who *does* have Docker, but the primary dev path is **native Postgres 16 + Redis 7 on Windows**, run via scripts in `scripts/`. The app talks to `localhost:5432` / `localhost:6379` either way, so nothing in the code depends on Docker specifically.

## Stack
As specified in the brief, with two adjustments (both allowed — "change only with a written reason"):
- **Python 3.12 pinned via a virtualenv** even though the system default is 3.14, because asyncpg/SQLAlchemy 2.0 async wheels and some pinned libs are most battle-tested on 3.12; the venv is created with whichever interpreter is available and we pin dependency versions instead if 3.12 isn't installable, documented in `backend/README.md`.
- **Background worker**: hand-rolled Redis-based worker (not ARQ). Reason: the worker's only jobs are (a) scan Postgres for expired holds/offers on a tick and (b) drain the outbox table to publish Redis pub/sub events — both are simple polling loops against Postgres as source of truth. Pulling in ARQ adds a second job-queue-with-its-own-semantics for no benefit here, since Postgres (not Redis) must stay authoritative per the brief's own requirement #2.

## Architecture

```
Next.js frontend  --HTTP/WS-->  FastAPI backend  --SQL-->  Postgres (source of truth)
                                       |  \
                                       |   --> Redis (hold accelerator, rate limits, pub/sub, queue)
                                       v
                                Worker process (expiry sweep, outbox drain, waitlist offers)
```

- **Routers** (thin, no business logic) → **Services** (business rules, state machine, locking strategy) → **Repositories** (SQLAlchemy queries).
- **Outbox pattern**: every state-changing service call writes its domain event into an `outbox_events` table in the *same transaction* as the state change. The worker polls `outbox_events` for unpublished rows, publishes to Redis pub/sub (for WebSocket fan-out) and marks them published. This guarantees "seat state changed" and "clients were told" never diverge, even across restarts.

## Data model (core tables)
- `users` (id, email, password_hash, role, created_at)
- `venues` (id, name, address)
- `halls` (id, venue_id, name)
- `sections` (id, hall_id, name, base_price)
- `seats` (id, hall_id, section_id, row_label, seat_number, UNIQUE(hall_id,row_label,seat_number))
- `events` (id, title, description, venue_id)
- `shows` (id, event_id, hall_id, starts_at, status)
- `show_seats` (id, show_id, seat_id, price, status ENUM[FREE,HELD,SOLD], UNIQUE(show_id, seat_id)) — **the hot table**. `status` is updated via a single conditional `UPDATE ... WHERE status = 'FREE'` (or SKIP LOCKED SELECT then UPDATE for holds) so the row is the lock.
- `bookings` (id, user_id, show_id, status ENUM[HELD,PAYMENT_PENDING,CONFIRMED,FAILED,EXPIRED,CANCELLED], idempotency_key, expires_at, total_amount, created_at, updated_at)
- `booking_seats` (booking_id, show_seat_id) — join table, also carries the per-seat price snapshot
- `idempotency_keys` (key, endpoint, request_hash, response_body, status_code, created_at) — generic replay cache for hold/pay/cancel
- `payments` (id, booking_id, provider_ref, status, raw_webhook_payload, created_at)
- `waitlist_entries` (id, show_id, section_id, user_id, position, status ENUM[WAITING,OFFERED,EXPIRED,CLAIMED,CANCELLED], offered_show_seat_id, offer_expires_at)
- `queue_tickets` (id, show_id, user_id, token, position, status, admitted_at) — waiting-room
- `outbox_events` (id, aggregate_type, aggregate_id, event_type, payload JSONB, published_at NULL)
- `audit_log` (id, actor, action, entity, entity_id, metadata JSONB, created_at) — also used by the optional ops agent

Indexes: `show_seats(show_id, status)`, `bookings(idempotency_key)`, `waitlist_entries(show_id, section_id, status, position)`, `outbox_events(published_at)` partial index `WHERE published_at IS NULL`.

## Locking strategy (documented properly in docs/design.md, decided now)
**Chosen: single conditional `UPDATE` per seat with `status = 'FREE'` in the `WHERE` clause, wrapped in one transaction per multi-seat hold, seats locked in a deterministic order (`ORDER BY show_seat_id`) to avoid deadlocks.**
- vs `SELECT ... FOR UPDATE SKIP LOCKED`: great for "give me any N free seats" (e.g. waitlist auto-assign), so we *do* use it there. Not used for "give me exactly seats A,B,C" because skipping a locked row when the user asked for a specific seat is the wrong behavior (should fail, not silently skip).
- vs advisory locks: unnecessary extra round trip when the row itself (`show_seats.status`) is the natural lock via the conditional UPDATE's atomicity — Postgres row-level locking during the UPDATE already serializes conflicting writers.
- Isolation level: `READ COMMITTED` (Postgres default) is sufficient because every write is a single conditional UPDATE (atomic check-and-set), not a read-then-write race.

## Milestones (build order — testing deferred to the end per instruction)
1. Repo scaffold: backend package layout, frontend scaffold, docker-compose.yml, native-service scripts, Alembic setup, seed script skeleton, auth.
2. Catalog schema + APIs (venues/halls/seats/events/shows) with all constraints/indexes.
3. Seat holds: atomic multi-seat hold, TTL, idempotency middleware/service.
4. Booking state machine, mock payment provider, webhook handling.
5. Expiry worker, outbox drain worker, WebSocket realtime channel.
6. Waitlist + virtual waiting room + Redis token-bucket rate limiting.
7. Frontend design system + browse + seat map (realtime).
8. Frontend checkout/tickets/my-bookings/waiting-room/admin dashboard.
9. Seed data + docs (design.md, failure-modes.md, benchmarks.md placeholder, Mermaid architecture diagram, README).
10. Testing pass (unit, concurrency, property-based, failure-injection) + fix bugs found, log them in docs/bugs-found.md. k6 script written but only run if you get Postgres/Redis running locally — I'll hand you the exact command.
11. Optional ops agent, only if 1–10 land clean.

## Risks / honest caveats
- I cannot execute anything here (no Postgres/Redis/Docker in this environment), so milestones 1–9 are built untested-by-me; correctness bugs are likely and will surface in milestone 10, which you'll need to actually run locally (I'll give exact commands) since I can't run Postgres myself.
- "500–5000 seats per show" seed data and a polished custom seat-map renderer is a lot of frontend work; I'll build it with plain SVG + CSS transforms (no heavy charting lib) for performance at that seat count.
- k6 benchmarks require a running stack on real hardware — I'll write the script and the doc template, but actual numbers must come from your machine.
