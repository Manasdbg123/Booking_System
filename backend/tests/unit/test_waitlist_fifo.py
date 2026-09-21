import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Booking, BookingStatus, ShowSeat, User, UserRole, WaitlistEntry, WaitlistStatus
from app.services import booking_service, hold_service, waitlist_service


async def _make_user(tag):
    async with SessionLocal() as session:
        u = User(email=f"wl-{tag}-{uuid.uuid4().hex[:6]}@test.dev", password_hash=hash_password("x"), role=UserRole.USER)
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return u.id


@pytest.mark.asyncio
async def test_waitlist_offer_goes_to_earliest_joiner_exactly_once(seeded_show):
    show = seeded_show["show"]
    section = seeded_show["section"]
    seat = seeded_show["seats"][0]

    holder_id = await _make_user("holder")
    waiter_ids = [await _make_user(f"waiter{i}") for i in range(5)]

    async with SessionLocal() as session:
        booking = await hold_service.create_hold(session, holder_id, show.id, [seat.id])

    # everyone else joins the waitlist for this section, in order
    entries = []
    for uid in waiter_ids:
        async with SessionLocal() as session:
            entries.append(await waitlist_service.join_waitlist(session, uid, show.id, section.id))

    # holder cancels -> seat frees -> exactly the first waiter should be offered it
    async with SessionLocal() as session:
        from sqlalchemy.orm import selectinload

        booking = await session.get(Booking, booking.id, options=[selectinload(Booking.seats)])
        await booking_service.cancel_booking(session, booking)

    async with SessionLocal() as session:
        rows = (await session.execute(select(WaitlistEntry).where(WaitlistEntry.show_id == show.id))).scalars().all()
        offered = [r for r in rows if r.status == WaitlistStatus.OFFERED]
        waiting = [r for r in rows if r.status == WaitlistStatus.WAITING]

    assert len(offered) == 1
    assert offered[0].user_id == waiter_ids[0], "the earliest joiner must be offered the seat (FIFO)"
    assert len(waiting) == 4

    async with SessionLocal() as session:
        show_seat = (await session.execute(select(ShowSeat).where(ShowSeat.show_id == show.id, ShowSeat.seat_id == seat.id))).scalar_one()
        assert show_seat.status == "HELD"


@pytest.mark.asyncio
async def test_concurrent_seat_frees_only_offer_seat_to_one_waiter_each(seeded_show):
    """Regression guard for the SKIP LOCKED claim: if two seats free up at
    the same instant, two DIFFERENT waiters should be offered seats — never
    the same waiter twice, and never zero when waiters are available."""
    show = seeded_show["show"]
    section = seeded_show["section"]
    seats = seeded_show["seats"][:2]

    holder_ids = [await _make_user(f"h{i}") for i in range(2)]
    waiter_ids = [await _make_user(f"w{i}") for i in range(2)]

    bookings = []
    for uid, seat in zip(holder_ids, seats):
        async with SessionLocal() as session:
            bookings.append(await hold_service.create_hold(session, uid, show.id, [seat.id]))

    for uid in waiter_ids:
        async with SessionLocal() as session:
            await waitlist_service.join_waitlist(session, uid, show.id, section.id)

    async def cancel(booking):
        async with SessionLocal() as session:
            from sqlalchemy.orm import selectinload

            b = await session.get(Booking, booking.id, options=[selectinload(Booking.seats)])
            await booking_service.cancel_booking(session, b)

    await asyncio.gather(*[cancel(b) for b in bookings])

    async with SessionLocal() as session:
        offered = (await session.execute(select(WaitlistEntry).where(WaitlistEntry.status == WaitlistStatus.OFFERED))).scalars().all()

    assert len(offered) == 2
    assert {e.user_id for e in offered} == set(waiter_ids), "both waiters should get an offer, not one waiter getting both"
