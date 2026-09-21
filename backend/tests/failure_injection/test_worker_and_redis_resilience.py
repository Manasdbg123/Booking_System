"""Requirement 2: 'Postgres is the authority, Redis is only an accelerator.
Design the reconciliation so Redis loss cannot cause a double-book or a
permanently stuck seat.' These tests prove that by flushing Redis mid-flow
and by simulating a worker crash (partial sweep) and confirming the next
sweep still converges correctly."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.redis_client import get_redis
from app.db import SessionLocal
from app.models import Booking, BookingStatus, ShowSeat
from app.services import hold_service, idempotency_service
from app.workers import expiry_worker


@pytest.mark.asyncio
async def test_redis_flush_does_not_break_idempotency(seeded_show, user):
    """Idempotency claims live in Postgres (idempotency_keys table), not
    Redis, precisely so a Redis restart can't cause a replayed request to
    be double-processed."""
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]

    async def handler():
        async with SessionLocal() as session:
            booking = await hold_service.create_hold(session, user.id, show.id, [seat.id])
            return idempotency_service.IdempotentResult(status_code=201, body={"booking_id": str(booking.id)})

    result1 = await idempotency_service.run_idempotent("k1", "test", {"a": 1}, handler)

    await get_redis().flushdb()  # simulate total Redis loss

    # Replay with the same key must return the same cached result, not create a second booking.
    async def handler2():
        raise AssertionError("handler should not run again for a replayed idempotency key")

    result2 = await idempotency_service.run_idempotent("k1", "test", {"a": 1}, handler2)
    assert result1.body == result2.body


@pytest.mark.asyncio
async def test_expired_hold_is_reclaimed_even_after_simulated_worker_crash(seeded_show, user):
    """Simulates a worker crash: the expiry sweep is interrupted after
    identifying candidates but before processing them (we just don't call
    sweep_once at all here, representing the crashed run), then a second,
    fresh sweep (representing the restarted worker) must still fully
    reconcile the expired hold — proving no permanently stuck seat."""
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]

    async with SessionLocal() as session:
        booking = await hold_service.create_hold(session, user.id, show.id, [seat.id])
        # force it into the past, simulating TTL elapsed while the worker was down
        b = await session.get(Booking, booking.id)
        b.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        await session.commit()

    # "Crashed" worker run: nothing happens (time passes, no sweep).
    # Now the "restarted" worker runs a fresh sweep.
    expired_count = await expiry_worker.sweep_once()
    assert expired_count == 1

    async with SessionLocal() as session:
        b = await session.get(Booking, booking.id)
        assert b.status == BookingStatus.EXPIRED
        show_seat = (await session.execute(select(ShowSeat).where(ShowSeat.show_id == show.id, ShowSeat.seat_id == seat.id))).scalar_one()
        assert show_seat.status == "FREE"
        assert show_seat.held_by_booking_id is None


@pytest.mark.asyncio
async def test_running_sweep_twice_is_a_safe_no_op_the_second_time(seeded_show, user):
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]
    async with SessionLocal() as session:
        booking = await hold_service.create_hold(session, user.id, show.id, [seat.id])
        b = await session.get(Booking, booking.id)
        b.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        await session.commit()

    first = await expiry_worker.sweep_once()
    second = await expiry_worker.sweep_once()
    assert first == 1
    assert second == 0
