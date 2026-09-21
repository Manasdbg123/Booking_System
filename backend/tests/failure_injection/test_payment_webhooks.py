import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Booking, BookingStatus, Payment, PaymentStatus, ShowSeat
from app.services import booking_service, hold_service


async def _hold_and_pay(user_id, show_id, seat_id):
    async with SessionLocal() as session:
        booking = await hold_service.create_hold(session, user_id, show_id, [seat_id])
    async with SessionLocal() as session:
        booking = await booking_service.get_booking(session, booking.id)
        booking = await booking_service.initiate_payment(session, booking)
        provider_ref = f"test_{uuid.uuid4().hex}"
        await booking_service.record_payment_pending(session, booking.id, provider_ref, booking.total_amount)
    return booking.id, provider_ref


@pytest.mark.asyncio
async def test_duplicate_webhook_is_idempotent(seeded_show, user):
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]
    booking_id, provider_ref = await _hold_and_pay(user.id, show.id, seat.id)

    async with SessionLocal() as session:
        outcome1 = await booking_service.handle_webhook(session, provider_ref, booking_id, "SUCCEEDED")
    async with SessionLocal() as session:
        outcome2 = await booking_service.handle_webhook(session, provider_ref, booking_id, "SUCCEEDED")

    assert outcome1 == "confirmed"
    assert outcome2 == "already_processed"

    async with SessionLocal() as session:
        booking = await session.get(Booking, booking_id)
        assert booking.status == BookingStatus.CONFIRMED
        payment = (await session.execute(select(Payment).where(Payment.provider_ref == provider_ref))).scalar_one()
        assert payment.status == PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_concurrent_duplicate_webhooks_confirm_exactly_once(seeded_show, user):
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]
    booking_id, provider_ref = await _hold_and_pay(user.id, show.id, seat.id)

    async def deliver():
        async with SessionLocal() as session:
            return await booking_service.handle_webhook(session, provider_ref, booking_id, "SUCCEEDED")

    results = await asyncio.gather(*[deliver() for _ in range(10)])
    assert results.count("confirmed") == 1
    assert results.count("already_processed") == 9


@pytest.mark.asyncio
async def test_late_payment_success_after_expiry_reacquires_free_seat(seeded_show, user):
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]
    booking_id, provider_ref = await _hold_and_pay(user.id, show.id, seat.id)

    # Simulate the hold TTL elapsing (and the expiry worker having run) by
    # forcing the booking straight to EXPIRED and freeing the seat, exactly
    # as the worker would.
    async with SessionLocal() as session:
        from sqlalchemy.orm import selectinload

        booking = await session.get(Booking, booking_id, options=[selectinload(Booking.seats)])
        await hold_service.release_hold(session, booking, "expired")
        await session.commit()

    async with SessionLocal() as session:
        show_seat = (await session.execute(select(ShowSeat).where(ShowSeat.show_id == show.id, ShowSeat.seat_id == seat.id))).scalar_one()
        assert show_seat.status == "FREE"

    # The late webhook arrives after expiry — seat is still free, so it should re-acquire and confirm.
    async with SessionLocal() as session:
        outcome = await booking_service.handle_webhook(session, provider_ref, booking_id, "SUCCEEDED")
    assert outcome == "confirmed_late_reacquired"

    async with SessionLocal() as session:
        booking = await session.get(Booking, booking_id)
        assert booking.status == BookingStatus.CONFIRMED
        show_seat = (await session.execute(select(ShowSeat).where(ShowSeat.show_id == show.id, ShowSeat.seat_id == seat.id))).scalar_one()
        assert show_seat.status == "SOLD"


@pytest.mark.asyncio
async def test_late_payment_success_after_expiry_and_seat_resold_triggers_refund(seeded_show, user):
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]
    booking_id, provider_ref = await _hold_and_pay(user.id, show.id, seat.id)

    async with SessionLocal() as session:
        from sqlalchemy.orm import selectinload

        booking = await session.get(Booking, booking_id, options=[selectinload(Booking.seats)])
        await hold_service.release_hold(session, booking, "expired")
        await session.commit()

    # Someone else grabs the now-free seat and it gets sold before the late webhook arrives.
    async with SessionLocal() as session:
        import uuid as uuid_mod

        from app.core.security import hash_password
        from app.models import User, UserRole

        other = User(email=f"other-{uuid_mod.uuid4().hex[:8]}@test.dev", password_hash=hash_password("x"), role=UserRole.USER)
        session.add(other)
        await session.commit()
        await session.refresh(other)
        other_booking = await hold_service.create_hold(session, other.id, show.id, [seat.id])

    async with SessionLocal() as session:
        outcome = await booking_service.handle_webhook(session, provider_ref, booking_id, "SUCCEEDED")
    assert outcome == "refunded_seats_gone"

    async with SessionLocal() as session:
        booking = await session.get(Booking, booking_id)
        assert booking.status == BookingStatus.EXPIRED  # never resurrected
        payment = (await session.execute(select(Payment).where(Payment.provider_ref == provider_ref))).scalar_one()
        assert payment.status == PaymentStatus.REFUNDED
        # the other user's hold on the seat must be untouched
        show_seat = (await session.execute(select(ShowSeat).where(ShowSeat.show_id == show.id, ShowSeat.seat_id == seat.id))).scalar_one()
        assert show_seat.status == "HELD"
        assert str(show_seat.held_by_booking_id) == str(other_booking.id)


@pytest.mark.asyncio
async def test_out_of_order_failure_after_success_does_not_downgrade(seeded_show, user):
    """A FAILED webhook delivered after a SUCCEEDED one for the same
    provider_ref must be a no-op — payment.status is already terminal."""
    show = seeded_show["show"]
    seat = seeded_show["seats"][0]
    booking_id, provider_ref = await _hold_and_pay(user.id, show.id, seat.id)

    async with SessionLocal() as session:
        await booking_service.handle_webhook(session, provider_ref, booking_id, "SUCCEEDED")
    async with SessionLocal() as session:
        outcome = await booking_service.handle_webhook(session, provider_ref, booking_id, "FAILED")

    assert outcome == "already_processed"
    async with SessionLocal() as session:
        booking = await session.get(Booking, booking_id)
        assert booking.status == BookingStatus.CONFIRMED
