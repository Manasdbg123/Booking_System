"""The core guarantee: N concurrent clients fighting for the same seats must
never double-book, and exactly one winner per seat must succeed."""

import asyncio

import pytest

from app.db import SessionLocal
from app.services import hold_service
from tests.conftest import create_users


async def _attempt_hold(user_id, show_id, seat_ids):
    async with SessionLocal() as session:
        try:
            booking = await hold_service.create_hold(session, user_id, show_id, seat_ids)
            return ("ok", booking.id)
        except hold_service.SeatsUnavailableError:
            return ("conflict", None)


@pytest.mark.asyncio
async def test_500_concurrent_holds_on_one_seat_yields_exactly_one_winner(seeded_show):
    show = seeded_show["show"]
    target_seat = seeded_show["seats"][0]

    user_ids = await create_users(500)

    results = await asyncio.gather(*[_attempt_hold(uid, show.id, [target_seat.id]) for uid in user_ids])

    successes = [r for r in results if r[0] == "ok"]
    conflicts = [r for r in results if r[0] == "conflict"]

    assert len(successes) == 1, f"expected exactly 1 winner, got {len(successes)}"
    assert len(conflicts) == 499

    async with SessionLocal() as session:
        from sqlalchemy import select
        from app.models import ShowSeat

        show_seat = (
            await session.execute(select(ShowSeat).where(ShowSeat.show_id == show.id, ShowSeat.seat_id == target_seat.id))
        ).scalar_one()
        assert show_seat.status == "HELD"
        assert str(show_seat.held_by_booking_id) == str(successes[0][1])


@pytest.mark.asyncio
async def test_concurrent_holds_across_many_seats_no_double_booking(seeded_show):
    """500 clients, each requesting 2 random seats from a pool of 50 —
    verifies the aggregate invariant: every HELD seat is held by exactly
    one booking, and total held+free == total seats."""
    import random

    show = seeded_show["show"]
    seat_ids = [s.id for s in seeded_show["seats"]]

    user_ids = await create_users(500)

    async def attempt(uid):
        picks = random.sample(seat_ids, 2)
        return await _attempt_hold(uid, show.id, picks)

    results = await asyncio.gather(*[attempt(uid) for uid in user_ids])
    successes = [r for r in results if r[0] == "ok"]
    assert len(successes) >= 1

    async with SessionLocal() as session:
        from sqlalchemy import select, func
        from app.models import ShowSeat, BookingSeat

        rows = (
            await session.execute(
                select(BookingSeat.show_seat_id, func.count()).group_by(BookingSeat.show_seat_id).having(func.count() > 1)
            )
        ).all()
        assert rows == [], f"a show_seat was claimed by more than one booking_seats row: {rows}"

        counts = (await session.execute(select(ShowSeat.status, func.count()).where(ShowSeat.show_id == show.id).group_by(ShowSeat.status))).all()
        total = sum(c for _, c in counts)
        assert total == 50
