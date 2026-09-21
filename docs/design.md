# SeatRush — Design & Trade-offs

## 1. Locking strategy for seat holds

Three options were considered for the hottest path — claiming a seat:

| Approach | How it works | Verdict |
|---|---|---|
| `SELECT ... FOR UPDATE SKIP LOCKED` | Lock candidate rows, skip ones already locked, then check/update | Great for "give me *any* N available seats" (used here for waitlist auto-assign and queue-batch admission). Wrong fit for "give me *exactly* seats A, B, C" — skipping a locked seat the user explicitly asked for should surface as a conflict, not silently skip to a different seat. |
| Advisory locks (`pg_advisory_xact_lock`) | Take an app-level lock keyed by seat id before touching the row | Adds a round trip and a second locking primitive to reason about, for no benefit over option 3 below — the row itself already provides the right serialization point. |
| **Single conditional `UPDATE ... WHERE status = 'FREE'` per seat, in one transaction, seats ordered deterministically** | The predicate check and the write are the same atomic statement; Postgres's row-level locking during the UPDATE is the concurrency control | **Chosen.** No read-then-write gap to protect, no extra lock primitive, and correctness is enforced by the database, not application logic. |

**Multi-seat atomicity + no deadlocks:** for a hold on seats [A, B, C], all
three conditional UPDATEs run in one transaction, and the seats are always
processed in ascending `show_seats.id` order (`ORDER BY ShowSeat.id` in the
query that loads them). Every concurrent caller that might contend for an
overlapping seat set acquires row locks in that same global order, which is
the standard technique for deadlock-freedom: a cycle in the wait-for graph
is impossible when everyone locks in the same order. If any seat in the
request is already non-FREE, the whole transaction rolls back (see
`hold_service.create_hold` in `backend/app/services/hold_service.py`) — no
partial holds are ever left behind. This is covered by
`tests/concurrency/test_idempotency_and_multiseat.py::test_multiseat_hold_is_all_or_nothing`.

**Isolation level:** Postgres's default `READ COMMITTED` is sufficient.
There is no read-then-decide-then-write window in the hot path — the
conditional UPDATE folds the read and write into one atomic statement — so
the classic READ COMMITTED anomalies (non-repeatable reads, phantom reads)
don't apply to this code path.

## 2. The outbox pattern

Every service call that changes booking/seat state writes a row to
`outbox_events` in the *same transaction* as the state change (see
`app/services/outbox_service.py`, called from `hold_service`,
`booking_service`, `waitlist_service`). A separate worker
(`app/workers/outbox_worker.py`) polls for unpublished rows and publishes
them to Redis pub/sub for the WebSocket layer to fan out. Because the
outbox row and the state change commit together or not at all, a crash
between "seat flipped to SOLD" and "client notified" is impossible — the
notification is either both durably queued or the whole transaction never
happened.

## 3. Reconciliation without Redis (requirement 2)

Redis is used only as an accelerator (rate limiting, pub/sub, nothing that
holds authoritative state). The expiry worker
(`app/workers/expiry_worker.py`) reads its work list — which bookings have
passed `expires_at` — directly from Postgres. If Redis is flushed or
restarted entirely, this loop is completely unaffected: it never consulted
Redis in the first place. If the worker process itself crashes mid-sweep,
the next tick (from a restarted instance, or a second instance) re-queries
Postgres for the same still-expired rows and finishes the job — see
`tests/failure_injection/test_worker_and_redis_resilience.py`.

Idempotency keys are similarly stored in Postgres
(`idempotency_keys` table), not Redis, for the same reason: a Redis outage
must not turn a safe replay into a duplicate charge or a duplicate hold.

## 4. Hottest query & its index

The single most frequent query in the system is the seat map read:

```sql
SELECT * FROM show_seats WHERE show_id = :show_id;
```
(and, during a hold, `... WHERE id = :show_seat_id AND status = 'FREE'`,
run once per seat in the request).

Supporting index (from migration `0001_initial_schema.py`):
```sql
CREATE INDEX ix_show_seats_show_status ON show_seats (show_id, status);
```
With this composite index, both the full seat-map read (filtered on
`show_id`) and the "how many seats are still FREE for this section" checks
used by the admin heatmap and waitlist logic can be served by an index
scan rather than a sequential scan, even at the upper end of the brief's
seat-count range (5,000 seats/show).

**Verified plan** (Postgres 16.15, 5,000-seat show, after `ANALYZE show_seats`):

```
EXPLAIN ANALYZE SELECT * FROM show_seats WHERE show_id = 'aec633ed-...';

 Bitmap Heap Scan on show_seats  (cost=59.03..293.53 rows=5000 width=85)
                                 (actual time=0.098..0.392 rows=5000 loops=1)
   Recheck Cond: (show_id = 'aec633ed-...'::uuid)
   Heap Blocks: exact=58
   ->  Bitmap Index Scan on ix_show_seats_show_status
                                 (cost=0.00..57.78 rows=5000 width=0)
                                 (actual time=0.088..0.089 rows=5000 loops=1)
         Index Cond: (show_id = 'aec633ed-...'::uuid)
 Planning Time: 0.676 ms
 Execution Time: 0.531 ms
```

The composite index is used as intended (no sequential scan); 0.53 ms to
pull all 5,000 seat rows. Postgres picks a bitmap heap scan rather than a
plain index scan because the query returns the whole show — that's the
right choice at this selectivity, and it touches only 58 heap blocks.

The per-seat conditional UPDATE on the hold path hits the primary key:

```
EXPLAIN ANALYZE UPDATE show_seats SET version = version
                WHERE id = '61167291-...' AND status = 'FREE';

 Update on show_seats  (cost=0.29..8.30 rows=0 width=0)
                       (actual time=0.274..0.274 rows=0 loops=1)
   ->  Index Scan using show_seats_pkey on show_seats
                       (cost=0.29..8.30 rows=1 width=10)
                       (actual time=0.027..0.028 rows=1 loops=1)
         Index Cond: (id = '61167291-...'::uuid)
         Filter: (status = 'FREE'::seat_status)
 Planning Time: 1.960 ms
 Execution Time: 0.413 ms
```

End to end, the `/api/shows/{id}/seatmap` endpoint serves that 5,000-seat
show in ~170–270 ms (measured over the local loopback, including JSON
serialization of all 5,000 seats — serialization, not the query, dominates).

## 5. Idempotency

`idempotency_keys (key, endpoint)` is a composite primary key. A request
claims it with `INSERT ... ON CONFLICT DO NOTHING RETURNING key` — exactly
one concurrent request "wins" the insert. The winner runs the handler and
writes the result back; every other concurrent request with the same key
polls the row until it's no longer `in_progress`, then returns the same
cached response. A key reused with a materially different request body
(different seat ids, different booking id, etc.) is rejected with 422
instead of silently returning a mismatched cached result. See
`app/services/idempotency_service.py` and the concurrency test
`test_concurrent_duplicate_idempotency_keys_run_handler_once`.

## 6. Payment safety & the late-success race (requirement 4)

The booking state machine is enforced in exactly one place
(`booking_service._VALID_TRANSITIONS` / `_assert_transition`). The
interesting edge case is a payment webhook succeeding *after* the hold
already expired:
- If the seats are still FREE, `_try_reacquire_seats` re-claims them with
  the same conditional-UPDATE-in-deterministic-order pattern used by
  `create_hold`, then the booking transitions `EXPIRED -> CONFIRMED`.
- If any seat was taken by someone else in the meantime, the payment is
  marked `REFUNDED` (simulated — this is a mock provider) and the booking
  stays `EXPIRED`. It is never resurrected over another confirmed
  booking's seats.

Both branches are covered by
`tests/failure_injection/test_payment_webhooks.py`.

## 7. Waitlist fairness

Offering a freed seat to the next waiter uses:
```sql
UPDATE waitlist_entries SET status='OFFERED', ...
WHERE id = (
  SELECT id FROM waitlist_entries
  WHERE show_id=... AND section_id=... AND status='WAITING'
  ORDER BY position FOR UPDATE SKIP LOCKED LIMIT 1
) RETURNING id, user_id;
```
`ORDER BY position` enforces FIFO; `SKIP LOCKED` means two seats freeing up
at the same instant never race for the same waiting entry — each claims a
different one. See `tests/unit/test_waitlist_fifo.py`.
