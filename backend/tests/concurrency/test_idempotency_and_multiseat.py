import asyncio

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import BookingSeat, ShowSeat
from app.services import hold_service, idempotency_service


@pytest.mark.asyncio
async def test_concurrent_duplicate_idempotency_keys_run_handler_once(seeded_show, user):
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]
    call_count = 0

    async def handler():
        nonlocal call_count
        call_count += 1
        async with SessionLocal() as session:
            booking = await hold_service.create_hold(session, user.id, show.id, [seat.id])
            return idempotency_service.IdempotentResult(status_code=201, body={"booking_id": str(booking.id)})

    results = await asyncio.gather(
        *[idempotency_service.run_idempotent("dup-key", "test-endpoint", {"seat": str(seat.id)}, handler) for _ in range(20)]
    )

    assert call_count == 1, "handler must run exactly once despite 20 concurrent requests with the same key"
    booking_ids = {r.body["booking_id"] for r in results}
    assert len(booking_ids) == 1, "all replays must return the same booking"


@pytest.mark.asyncio
async def test_multiseat_hold_is_all_or_nothing(seeded_show, user):
    """Two seats, one already HELD by someone else — the multi-seat hold
    for [free_seat, taken_seat] must acquire NEITHER seat."""
    show = seeded_show["show"]
    free_seat, taken_seat = seeded_show["seats"][0], seeded_show["seats"][1]

    async with SessionLocal() as session:
        import uuid

        from app.core.security import hash_password
        from app.models import User, UserRole

        other = User(email=f"other-{uuid.uuid4().hex[:8]}@test.dev", password_hash=hash_password("x"), role=UserRole.USER)
        session.add(other)
        await session.commit()
        await session.refresh(other)
        await hold_service.create_hold(session, other.id, show.id, [taken_seat.id])

    async with SessionLocal() as session:
        with pytest.raises(hold_service.SeatsUnavailableError) as exc_info:
            await hold_service.create_hold(session, user.id, show.id, [free_seat.id, taken_seat.id])
        assert taken_seat.id in exc_info.value.unavailable_seat_ids

    async with SessionLocal() as session:
        free_show_seat = (await session.execute(select(ShowSeat).where(ShowSeat.show_id == show.id, ShowSeat.seat_id == free_seat.id))).scalar_one()
        assert free_show_seat.status == "FREE", "the free seat must NOT be held when the sibling seat in the request failed"


@pytest.mark.asyncio
async def test_concurrent_multiseat_holds_no_deadlock_no_partial_holds(seeded_show):
    """Many clients requesting overlapping pairs of seats concurrently —
    deterministic lock ordering must prevent deadlocks, and every
    booking_seats row must belong to a booking that acquired ALL its
    requested seats (no partial holds anywhere)."""
    import random
    import uuid

    from app.core.security import hash_password
    from app.models import User, UserRole

    show = seeded_show["show"]
    seat_ids = [s.id for s in seeded_show["seats"]]

    async def make_user(n):
        async with SessionLocal() as session:
            u = User(email=f"multi-{n}-{uuid.uuid4().hex[:6]}@test.dev", password_hash=hash_password("x"), role=UserRole.USER)
            session.add(u)
            await session.commit()
            await session.refresh(u)
            return u.id

    user_ids = await asyncio.gather(*[make_user(i) for i in range(100)])

    async def attempt(uid):
        picks = random.sample(seat_ids, 3)
        async with SessionLocal() as session:
            try:
                booking = await hold_service.create_hold(session, uid, show.id, picks)
                return booking.id
            except hold_service.SeatsUnavailableError:
                return None

    results = await asyncio.wait_for(asyncio.gather(*[attempt(uid) for uid in user_ids]), timeout=30)
    winners = [r for r in results if r is not None]
    assert len(winners) >= 1  # no deadlock hang (asyncio.wait_for would have raised otherwise)

    async with SessionLocal() as session:
        for booking_id in winners:
            rows = (await session.execute(select(BookingSeat).where(BookingSeat.booking_id == booking_id))).scalars().all()
            assert len(rows) == 3, f"booking {booking_id} has a partial hold: {len(rows)} seats instead of 3"
