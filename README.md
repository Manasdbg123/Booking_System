# SeatRush

A high-concurrency ticket booking platform (BookMyShow/IRCTC-Tatkal style):
never double-book a seat, survive worker crashes and Redis loss, handle
payment webhooks safely, and stay fair under a traffic spike.

See [`PLAN.md`](PLAN.md) for architecture and milestones,
[`docs/design.md`](docs/design.md) for the locking-strategy rationale and
other trade-offs, [`docs/failure-modes.md`](docs/failure-modes.md) for what
happens when each dependency fails, and
[`docs/architecture.md`](docs/architecture.md) for diagrams.

## Guarantees, and where they're proven

| Guarantee | Enforced in | Proven by |
|---|---|---|
| Never double-book a seat | `app/services/hold_service.py` (conditional UPDATE, deterministic lock order) | `tests/concurrency/test_seat_contention.py` |
| Holds expire reliably, survive worker crash / Redis loss | `app/workers/expiry_worker.py` | `tests/failure_injection/test_worker_and_redis_resilience.py` |
| Idempotency-Key on all mutations | `app/services/idempotency_service.py` | `tests/concurrency/test_idempotency_and_multiseat.py` |
| Payment safety / state machine | `app/services/booking_service.py` | `tests/failure_injection/test_payment_webhooks.py` |
| Multi-seat holds atomic, no deadlocks | `app/services/hold_service.py` | `tests/concurrency/test_idempotency_and_multiseat.py` |
| Waitlist: exactly-once, FIFO | `app/services/waitlist_service.py` | `tests/unit/test_waitlist_fifo.py` |
| Waiting room + rate limiting | `app/services/queue_service.py`, `app/core/rate_limit.py` | k6 script (`k6/tatkal-spike.js`), not yet run — see below |

**All 32 tests pass** against real Postgres 16 + Redis (`pytest -q` →
`32 passed in 38.62s`). The headline result: 500 concurrent clients
contending for one seat yield **exactly 1 winner and 499 conflicts**, with
zero double-bookings. Getting there surfaced 7 real bugs — including two
genuine concurrency defects — all written up in
[`docs/bugs-found.md`](docs/bugs-found.md).

## Stack
FastAPI (async) + SQLAlchemy 2.0/asyncpg + Alembic + Postgres 16, Redis 7,
a hand-rolled worker process, Next.js (App Router) + TypeScript + Tailwind +
Framer Motion + TanStack Query, WebSocket realtime, pytest/Hypothesis/k6 for
testing.

## Running it

**With Docker** (if you have it): `docker compose up` from the repo root.

**Without Docker** (what this was actually built/documented against — see
[`docs/local-setup.md`](docs/local-setup.md) for full native-Windows setup
with Postgres + Redis installed directly, no virtualization):
```
cd backend && pip install -r requirements.txt && alembic upgrade head && python -m scripts.seed
uvicorn app.main:app --reload            # terminal 1
python -m app.workers.run_workers        # terminal 2
cd frontend && npm install && npm run dev  # terminal 3
```
Or once set up once: `scripts/run-local.ps1` opens all three for you.

Default admin login (bootstrapped on first API startup): see
`ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` in `.env.example`.

## Status (honest, as of writing)

**Verified running, end to end:**
- Alembic migration applies cleanly to Postgres 16; seed loads 7 events / ~15,100 seats.
- Full booking flow exercised live: register → seat map → hold → pay → async webhook → **CONFIRMED** with ticket code.
- Backend test suite: **32/32 passing** against real Postgres + Redis.
- Expiry worker verified live: a hold forced past its TTL was reclaimed and its seat returned to FREE within 1 second.
- Frontend: `npm run build`, `tsc --noEmit` and `next lint` all clean; every route returns HTTP 200 from the dev server.
- Hottest-query `EXPLAIN ANALYZE` captured and pasted into [`docs/design.md`](docs/design.md) — index scan confirmed, 0.53 ms for 5,000 seats.

**Not done:**
- **k6 benchmarks not run.** `k6/tatkal-spike.js` is written but k6 isn't installed here, so [`docs/benchmarks.md`](docs/benchmarks.md) is still an empty template. This is the main outstanding item.
- **No visual/browser verification of the UI.** Pages compile, render and return 200, and the API they call is verified working — but nobody has looked at the seat map in a browser, so visual polish, the zoom/pan interaction, and the live WebSocket seat updates are unconfirmed in practice.
- **Playwright UI tests** from the brief were not written.
- **Optional ops agent (milestone 11)** not started.
- Next.js is pinned to 14.2.35 (latest 14.x). `npm audit` still reports advisories that are only fixed in Next 16, which is a breaking major upgrade (async route params etc.) — deliberately not attempted.

## Optional ops agent
Not built — the brief says to do it last, only if everything else is solid.
Milestones 1–10 are now verified except the k6 benchmarks, so this is the
reasonable next thing to pick up after those numbers exist.
