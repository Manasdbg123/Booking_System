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

- Frontend verified visually and interactively via Playwright: **12/12 e2e tests pass** across desktop and mobile viewports (`cd frontend && npm run test:e2e`), covering browse, seat selection by mouse *and* keyboard, hold → pay → confirmed ticket, and my-bookings.

**Not done:**
- **k6 benchmarks not run.** `k6/tatkal-spike.js` is written but k6 isn't installed here, so [`docs/benchmarks.md`](docs/benchmarks.md) is still an empty template. This is the main outstanding item.
- **Live WebSocket seat updates are not covered by an automated test.** The outbox → Redis → WS path is verified at the backend level, but no test asserts that a second browser sees a seat grey out in real time.
- **Optional ops agent (milestone 11)** not started.
- Next.js is pinned to 14.2.35 (latest 14.x). `npm audit` still reports advisories that are only fixed in Next 16, which is a breaking major upgrade (async route params etc.) — deliberately not attempted.

## AI booking assistant
Built (milestone 11): a tool-calling AI agent (`/ai-assistant`, backed by
`/api/ai/chat`) that searches shows, checks live availability/pricing,
answers policy questions via RAG over `backend/app/knowledge/*.md`, and can
place holds, pay, or cancel bookings for the authenticated user — always
through the same service functions the REST API uses, never raw SQL, and
only after the user confirms in conversation. Every irreversible tool call
is audit-logged and visible in the admin dashboard's "AI activity log".
See [`docs/ai-agent.md`](docs/ai-agent.md) for the full architecture,
guardrails, and RAG-vs-vector-DB trade-off writeup.

Requires `GROQ_API_KEY` set (see `.env.example`); without it the endpoint
returns a clean 503 rather than failing silently. Runs against Groq's
OpenAI-compatible chat-completions API with `openai/gpt-oss-120b` (tool
calling verified live against that model — plain `llama-3.x` model ids are
not available on every Groq account/region, so the default is picked for
broad availability).

**Verified live**, not just unit-tested: with Postgres + Redis running and
a real `GROQ_API_KEY`, the full backend test suite (43 tests, including
`backend/tests/unit/test_ai_agent.py` with the Groq client mocked) passes;
the app was also started as a real `uvicorn` process and hit with real HTTP
requests confirming `/api/ai/chat` returns a clean 503 with no key, and
`/api/admin/analytics` / `/api/admin/ai-activity` return real data. A live
end-to-end chat turn against the real Groq API still needs to be exercised
through the UI once (k6 benchmarks remain the one outstanding item, as
before).
