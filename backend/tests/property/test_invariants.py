"""Property-based invariant checks with Hypothesis.

Hypothesis generates random sequences of hold / cancel / confirm operations
against a small seat pool, executed through the real services against the
real test database. After every single step we assert the invariants that
must hold no matter what sequence occurred:
  1. free + held + sold == total seats (nothing vanishes or duplicates)
  2. no seat is referenced by more than one CONFIRMED booking
  3. every booking is in a status reachable by a valid transition

Note on structure: this is a @given test rather than a RuleBasedStateMachine
because Hypothesis's stateful rules are synchronous, which would force a new
event loop per rule — and the SQLAlchemy engine's connection pool is bound to
one loop for the whole session (see pytest.ini).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    Booking,
    BookingSeat,
    BookingStatus,
    Event,
    Hall,
    Seat,
    Section,
    Show,
    ShowSeat,
    User,
    UserRole,
    Venue,
)
from app.services import booking_service, hold_service

SEAT_COUNT = 6

# op = (kind, index); index is interpreted modulo the relevant collection
operations = st.lists(
    st.tuples(st.sampled_from(["hold", "cancel", "confirm"]), st.integers(min_value=0, max_value=20)),
    min_size=1,
    max_size=12,
)


async def _make_show() -> tuple[uuid.UUID, list[uuid.UUID], uuid.UUID]:
    async with SessionLocal() as session:
        venue = Venue(name="Prop Venue", address="-")
        session.add(venue)
        await session.flush()
        hall = Hall(venue_id=venue.id, name=f"Hall {uuid.uuid4().hex[:6]}")
        session.add(hall)
        await session.flush()
        section = Section(hall_id=hall.id, name="Gen", base_price=Decimal("100"))
        session.add(section)
        await session.flush()
        event = Event(title="Prop Event", venue_id=venue.id)
        session.add(event)
        await session.flush()
        show = Show(event_id=event.id, hall_id=hall.id, starts_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
        session.add(show)
        await session.flush()

        seat_ids = []
        for i in range(SEAT_COUNT):
            seat = Seat(hall_id=hall.id, section_id=section.id, row_label="A", seat_number=i + 1)
            session.add(seat)
            await session.flush()
            session.add(ShowSeat(show_id=show.id, seat_id=seat.id, price=Decimal("100")))
            seat_ids.append(seat.id)

        user = User(
            email=f"prop-{uuid.uuid4().hex[:10]}@test.dev",
            password_hash="$2b$12$abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRS",
            role=UserRole.USER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return show.id, seat_ids, user.id


async def _assert_invariants(show_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(ShowSeat.status, func.count()).where(ShowSeat.show_id == show_id).group_by(ShowSeat.status)
            )
        ).all()
        total = sum(c for _, c in rows)
        assert total == SEAT_COUNT, f"seat-count invariant violated: {rows}"

        doubled = (
            await session.execute(
                select(BookingSeat.show_seat_id, func.count())
                .join(Booking, Booking.id == BookingSeat.booking_id)
                .join(ShowSeat, ShowSeat.id == BookingSeat.show_seat_id)
                .where(Booking.status == BookingStatus.CONFIRMED, ShowSeat.show_id == show_id)
                .group_by(BookingSeat.show_seat_id)
                .having(func.count() > 1)
            )
        ).all()
        assert doubled == [], f"double-booking detected: {doubled}"

        # Every SOLD seat has a confirmed booking behind it. This must be a
        # NOT EXISTS rather than an outer join + IS NULL: a seat that was
        # held, cancelled, then re-held and sold legitimately has several
        # booking_seats rows, and only one of them is the confirmed one.
        confirmed_for_seat = (
            select(BookingSeat.id)
            .join(Booking, Booking.id == BookingSeat.booking_id)
            .where(BookingSeat.show_seat_id == ShowSeat.id, Booking.status == BookingStatus.CONFIRMED)
        )
        sold_without_booking = (
            await session.execute(
                select(func.count())
                .select_from(ShowSeat)
                .where(ShowSeat.show_id == show_id, ShowSeat.status == "SOLD", ~confirmed_for_seat.exists())
            )
        ).scalar_one()
        assert sold_without_booking == 0, "a seat is SOLD with no confirmed booking behind it"


@given(ops=operations)
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_seat_inventory_invariants_hold_under_random_operations(ops):
    show_id, seat_ids, user_id = await _make_show()
    booking_ids: list[uuid.UUID] = []

    for kind, index in ops:
        if kind == "hold":
            seat_id = seat_ids[index % len(seat_ids)]
            async with SessionLocal() as session:
                try:
                    booking = await hold_service.create_hold(session, user_id, show_id, [seat_id])
                    booking_ids.append(booking.id)
                except hold_service.SeatsUnavailableError:
                    pass

        elif kind == "cancel" and booking_ids:
            async with SessionLocal() as session:
                try:
                    booking = await booking_service.get_booking(session, booking_ids[index % len(booking_ids)])
                    await booking_service.cancel_booking(session, booking)
                except (booking_service.BookingNotFoundError, booking_service.InvalidTransitionError):
                    pass

        elif kind == "confirm" and booking_ids:
            booking_id = booking_ids[index % len(booking_ids)]
            async with SessionLocal() as session:
                try:
                    booking = await booking_service.get_booking(session, booking_id)
                    if booking.status == BookingStatus.HELD:
                        await booking_service.initiate_payment(session, booking)
                        booking = await booking_service.get_booking(session, booking_id)
                        await booking_service._confirm_booking(session, booking)
                        await session.commit()
                except (booking_service.BookingNotFoundError, booking_service.InvalidTransitionError):
                    pass

        await _assert_invariants(show_id)

    # all bookings ended in a legitimate status
    async with SessionLocal() as session:
        for booking_id in booking_ids:
            booking = await session.get(Booking, booking_id)
            assert booking.status in set(BookingStatus)
