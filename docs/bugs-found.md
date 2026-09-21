# Bugs found

Bugs caught while building and then actually running the stack (Postgres 16
+ Redis + the full pytest suite). Each entry: what failed, root cause, fix,
and what now guards it.

The two that matter most for the brief's guarantees are **#5 (bcrypt
blocking the event loop)** and **#6 (webhook idempotency race)** — both were
found by the concurrency tests, not by reading the code.

---

## 1. Payment failure mislabeled a booking as CANCELLED instead of FAILED

**Found by:** code review, before the suite ran.

**Root cause:** `handle_webhook`'s failure branch called
`hold_service.release_hold(..., "cancelled")`, which both frees the seats
*and* sets `booking.status = CANCELLED` internally. The caller then tried to
overwrite it back to `FAILED`, but `release_hold` had already emitted a
`booking.cancelled` outbox event, and a concurrent reader could observe
`CANCELLED` for a booking that should read `FAILED`. Those are semantically
different terminal states (user cancelled vs. payment declined) and
conflating them corrupts any conversion analysis.

**Fix:** split `release_hold` (frees seats *and* sets a terminal status,
used by expiry/cancellation) from `free_held_seats` (frees seats only,
caller owns the status). The failure branch now uses `free_held_seats`, sets
`FAILED` itself, and emits its own `booking.failed` event.

---

## 2. Seed script crashed on any show larger than ~2,080 seats

**Found by:** running `python -m scripts.seed`.

```
IndexError: list index out of range   (seed.py, make_seats)
```

**Root cause:** row labels were built as a fixed list of 52 (`A`–`Z` plus
`AA`–`AZ`), but at 40 seats/row a 5,000-seat show needs 125 rows. The brief
explicitly asks for shows up to 5,000 seats, so this hit on the second
event.

**Fix:** replaced the fixed list with a spreadsheet-style label generator
(`A..Z, AA..AZ, BA..`) that never runs out.

---

## 3. Seats and sections collided when two events shared a hall

**Found by:** running the seed script (would have raised on
`uq_seat_position` once bug #2 was fixed).

**Root cause:** the seed cycled 7 events over 4 venues and reused each
venue's single hall, but seats and sections are hall-scoped. The second
event on a hall tried to insert seats at row/number positions that already
existed, violating `uq_seat_position`. The original code papered over this
by skipping already-existing seats — which silently produced shows with
almost no `show_seats` rows, i.e. an apparently sold-out show.

**Fix:** each event gets its own hall within its venue, so seat and section
namespaces never overlap. The "skip existing seats" workaround is gone.

---

## 4. `/api/events` returned 500 — missing ORM relationship

**Found by:** first live request against the running API.

```
AttributeError: type object 'Event' has no attribute 'venue'
```

**Root cause:** `Event` had a `venue_id` column but no `venue` relationship,
while `EventOut` and `catalog_service.list_events` (via
`selectinload(Event.venue)`) both expected one. Nothing caught it earlier
because no test exercised the catalog read path and the app imports fine —
SQLAlchemy only fails when the attribute is actually accessed.

**Fix:** added `venue: Mapped[Venue] = relationship()` to `Event`.

---

## 5. bcrypt blocked the event loop, exhausting the DB connection pool

**Found by:** `tests/concurrency/test_seat_contention.py` — it didn't fail
an assertion, it *timed out*:

```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 20 reached,
connection timed out, timeout 30.00
```
(223 seconds, then failure.)

**Root cause:** `auth_service.register`/`login` called bcrypt
(`hash_password`/`verify_password`) synchronously inside async functions.
bcrypt is deliberately slow (~250 ms/call at cost 12) and holds the GIL, so
each call froze the *entire* event loop. Under concurrent registration every
request held a checked-out pooled connection while the loop was blocked on
someone else's hash, so connections were never returned and the pool
deadlocked itself into a timeout.

This is a genuine production bug, not a test artifact: any burst of
signups/logins would have stalled all other traffic — exactly the
Tatkal-spike scenario the project is built for.

**Fix:** `asyncio.to_thread(...)` around both bcrypt calls in
`auth_service`, so hashing runs on a worker thread and the loop stays free.

**Result:** the same test went from a 223 s timeout to **5.9 s**, and now
asserts exactly 1 winner / 499 conflicts on a contested seat.

---

## 6. Webhook idempotency check raced (TOCTOU) under concurrent delivery

**Found by:**
`tests/failure_injection/test_payment_webhooks.py::test_concurrent_duplicate_webhooks_confirm_exactly_once`
— 10 simultaneous deliveries of the same webhook returned:

```
['confirmed', 'already_confirmed', 'already_processed', x7]
assert 8 == 9
```

**Root cause:** `handle_webhook` read the payment row *without a lock* and
returned early if `payment.status != PENDING`. Two concurrent deliveries
could both read `PENDING` before either committed, so both passed the
idempotency gate. Only the second, deeper check (booking already
`CONFIRMED`) stopped the duplicate — meaning the actual guarantee was
resting on a fallback rather than on the idempotency gate itself.

Worth being precise: **no double-booking occurred** and exactly one
confirmation happened, so the safety property held. But the defense that
held was the last one in the chain, and the `already_confirmed` branch also
returned *without committing*, silently discarding the `payment.status`
update it had just made.

**Fix:** the payment row is now selected `FOR UPDATE`, so the PENDING check
and the subsequent status transition are atomic and concurrent deliveries
serialize. Lock order is payment row → booking row on every path, so the
added lock cannot deadlock against the existing one. The
already-confirmed branch now treats a *distinct* second successful payment
as a duplicate charge and refunds it (`refunded_duplicate_payment`) rather
than silently swallowing it.

---

## 7. `use_alter` foreign key had no name, breaking schema teardown

**Found by:** the first pytest run.

```
sqlalchemy.exc.CompileError: Can't emit DROP CONSTRAINT for constraint
ForeignKeyConstraint(...); it has no name
```

**Root cause:** `ShowSeat.held_by_booking_id` uses
`ForeignKey("bookings.id", use_alter=True)` because `show_seats` and
`bookings` reference each other circularly. `use_alter` constraints are
emitted as standalone `ADD`/`DROP CONSTRAINT` statements, which require a
stable name — Postgres auto-names it on CREATE, so the migration worked and
only teardown failed.

**Fix:** named it `fk_show_seats_held_by_booking` in both the model and
migration `0001`.

---

## Test-harness defects fixed along the way

Not product bugs, but they invalidated test results until fixed:

- **Event loop mismatch.** pytest-asyncio 1.x gives each test its own loop, but the SQLAlchemy engines are module-level singletons whose asyncpg pools bind to the first loop that touches them. Fixed by pinning `asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope = session` in `pytest.ini`.
- **Hypothesis stateful machine spun a new loop per rule** (`asyncio.new_event_loop()` per rule), which broke the shared pool. Rewritten as an async `@given` test that runs on the session loop.
- **False-positive invariant.** The "every SOLD seat has a confirmed booking" check used an outer join + `IS NULL`, which flags a seat that was held → cancelled → re-held → sold, because the cancelled booking's `booking_seats` row legitimately still exists. Hypothesis found this in 4 steps. Rewritten as a `NOT EXISTS` correlated subquery.
- **Fixtures passed ISO strings for `starts_at`;** asyncpg requires real `datetime` objects.
- **500 test users meant 500 bcrypt hashes** (~2 min of pure CPU). Test users now share one precomputed hash and are bulk-inserted in a single transaction.

## Environment issue (not a code bug)

`redis-py` ≥ 5 negotiates RESP3 by sending `HELLO 3` on connect; the Redis
5.0.14 Windows port used for local dev predates `HELLO` (added in Redis 6)
and errors. The client now pins `protocol=2`, which every targeted server
version understands, and nothing here needs RESP3 features.
