"""Booking state machine + payment orchestration.

State machine (the ONE place transitions are validated):
  HELD -> PAYMENT_PENDING -> CONFIRMED
  HELD -> PAYMENT_PENDING -> FAILED
  HELD -> EXPIRED                      (hold TTL elapsed, no payment attempt)
  HELD -> CANCELLED                    (user cancels before paying)
  PAYMENT_PENDING -> EXPIRED           (hold TTL elapsed while payment in flight)
  EXPIRED -> CONFIRMED                 (late payment success, seats still free — re-acquired)
  EXPIRED -> (stays EXPIRED, payment refunded) (late payment success, seats taken by someone else)

Any transition not listed above is rejected by _assert_transition.
"""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Booking, BookingStatus, Payment, PaymentStatus
from app.services import hold_service, outbox_service, waitlist_service

_VALID_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.HELD: {BookingStatus.PAYMENT_PENDING, BookingStatus.EXPIRED, BookingStatus.CANCELLED},
    BookingStatus.PAYMENT_PENDING: {BookingStatus.CONFIRMED, BookingStatus.FAILED, BookingStatus.EXPIRED},
    BookingStatus.EXPIRED: {BookingStatus.CONFIRMED},  # late-success re-acquire path only
    BookingStatus.CONFIRMED: set(),
    BookingStatus.FAILED: set(),
    BookingStatus.CANCELLED: set(),
}


class InvalidTransitionError(Exception):
    pass


class BookingNotFoundError(Exception):
    pass


def _assert_transition(current: BookingStatus, target: BookingStatus) -> None:
    if target not in _VALID_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(f"Cannot transition booking from {current} to {target}")


async def get_booking(session: AsyncSession, booking_id: uuid.UUID) -> Booking:
    booking = await session.get(
        Booking, booking_id, options=[selectinload(Booking.seats)]
    )
    if booking is None:
        raise BookingNotFoundError()
    return booking


async def initiate_payment(session: AsyncSession, booking: Booking) -> Booking:
    now = datetime.now(timezone.utc)
    if booking.expires_at and booking.expires_at < now:
        await expire_booking(session, booking)
        await session.commit()
        raise InvalidTransitionError("Hold already expired")

    _assert_transition(booking.status, BookingStatus.PAYMENT_PENDING)
    booking.status = BookingStatus.PAYMENT_PENDING
    await outbox_service.emit(
        session, "booking", str(booking.id), "booking.payment_pending", {"booking_id": str(booking.id)}
    )
    await session.commit()
    return booking


async def record_payment_pending(session: AsyncSession, booking_id: uuid.UUID, provider_ref: str, amount) -> None:
    session.add(Payment(booking_id=booking_id, provider_ref=provider_ref, status=PaymentStatus.PENDING, amount=amount))
    await session.commit()


async def handle_webhook(session: AsyncSession, provider_ref: str, booking_id: uuid.UUID, status: str) -> str:
    """Returns a short outcome string for logging/testing. Idempotent: safe to
    call twice with the same provider_ref+status (duplicate webhooks), and
    safe under concurrent delivery of the same webhook.

    Locks are taken payment-row first, then booking-row, in that order on
    every path, so concurrent deliveries serialize without deadlocking.
    """

    # FOR UPDATE, not a plain read: the "is this payment still PENDING?"
    # check and the status transition that follows must be atomic. Reading
    # without the lock lets two concurrent deliveries of the same webhook
    # both observe PENDING and both proceed.
    payment = (
        await session.execute(select(Payment).where(Payment.provider_ref == provider_ref).with_for_update())
    ).scalar_one_or_none()
    if payment is None:
        return "unknown_provider_ref"

    if payment.status != PaymentStatus.PENDING:
        return "already_processed"  # duplicate/out-of-order webhook — no-op

    # Row-lock the booking so concurrent webhooks for different payments on
    # the same booking serialize instead of racing each other.
    await session.execute(text("SELECT id FROM bookings WHERE id = :id FOR UPDATE"), {"id": str(booking_id)})
    booking = await get_booking(session, booking_id)

    if status != "SUCCEEDED":
        payment.status = PaymentStatus.FAILED
        if booking.status == BookingStatus.PAYMENT_PENDING:
            _assert_transition(booking.status, BookingStatus.FAILED)
            show_seat_ids = await hold_service.free_held_seats(session, booking)
            booking.status = BookingStatus.FAILED
            await outbox_service.emit(
                session, "booking", str(booking.id), "booking.failed",
                {"booking_id": str(booking.id), "show_id": str(booking.show_id), "seat_ids": [str(s) for s in show_seat_ids]},
            )
            await waitlist_service.try_offer_freed_seats(session, booking.show_id, show_seat_ids)
        await session.commit()
        return "payment_failed"

    payment.status = PaymentStatus.SUCCEEDED

    if booking.status == BookingStatus.PAYMENT_PENDING:
        await _confirm_booking(session, booking)
        await session.commit()
        return "confirmed"

    if booking.status == BookingStatus.EXPIRED:
        reacquired = await _try_reacquire_seats(session, booking)
        if reacquired:
            await _confirm_booking(session, booking, from_expired=True)
            await session.commit()
            return "confirmed_late_reacquired"
        else:
            payment.status = PaymentStatus.REFUNDED
            await outbox_service.emit(
                session,
                "payment",
                str(payment.id),
                "payment.refunded",
                {"booking_id": str(booking.id), "reason": "seats_no_longer_available_after_expiry"},
            )
            await session.commit()
            return "refunded_seats_gone"

    if booking.status == BookingStatus.CONFIRMED:
        # A *different* payment succeeding against an already-confirmed
        # booking (duplicate deliveries of the same payment are filtered out
        # above by the payment row lock), so the customer has paid twice.
        # Refund the extra; the booking is already theirs.
        payment.status = PaymentStatus.REFUNDED
        await outbox_service.emit(
            session, "payment", str(payment.id), "payment.refunded",
            {"booking_id": str(booking.id), "reason": "booking_already_confirmed_by_another_payment"},
        )
        await session.commit()
        return "refunded_duplicate_payment"

    # CANCELLED/FAILED with a late success — refund, never resurrect
    payment.status = PaymentStatus.REFUNDED
    await outbox_service.emit(
        session,
        "payment",
        str(payment.id),
        "payment.refunded",
        {"booking_id": str(booking.id), "reason": f"booking_was_{booking.status.value.lower()}"},
    )
    await session.commit()
    return "refunded_booking_terminal"


async def _confirm_booking(session: AsyncSession, booking: Booking, from_expired: bool = False) -> None:
    target = BookingStatus.CONFIRMED
    _assert_transition(booking.status, target)
    show_seat_ids = [bs.show_seat_id for bs in booking.seats]
    if not from_expired:
        # seats are already HELD by this booking; flip to SOLD
        await session.execute(
            text(
                "UPDATE show_seats SET status = 'SOLD', hold_expires_at = NULL, version = version + 1 "
                "WHERE id = ANY(:ids) AND held_by_booking_id = :booking_id"
            ),
            {"ids": [str(i) for i in show_seat_ids], "booking_id": str(booking.id)},
        )
    booking.status = target
    booking.ticket_code = secrets.token_hex(8).upper()
    await waitlist_service.mark_claimed_if_applicable(session, booking)
    await outbox_service.emit(
        session,
        "booking",
        str(booking.id),
        "booking.confirmed",
        {"booking_id": str(booking.id), "ticket_code": booking.ticket_code, "show_id": str(booking.show_id)},
    )


async def _try_reacquire_seats(session: AsyncSession, booking: Booking) -> bool:
    """Late payment success after hold expiry: attempt to re-claim the same
    seats directly to SOLD, same deterministic-order + conditional-UPDATE
    pattern as create_hold, so this can never double-book a seat someone
    else has since taken or held."""
    show_seat_ids = sorted([bs.show_seat_id for bs in booking.seats], key=str)
    for show_seat_id in show_seat_ids:
        result = await session.execute(
            text(
                "UPDATE show_seats SET status = 'SOLD', held_by_booking_id = :booking_id, "
                "hold_expires_at = NULL, version = version + 1 "
                "WHERE id = :id AND status = 'FREE'"
            ),
            {"booking_id": str(booking.id), "id": str(show_seat_id)},
        )
        if result.rowcount == 0:
            return False
    return True


async def expire_booking(session: AsyncSession, booking: Booking) -> None:
    """Shared by the pay-time lazy check and the expiry worker's sweep. Does
    NOT commit — caller controls the transaction boundary."""
    if booking.status not in (BookingStatus.HELD, BookingStatus.PAYMENT_PENDING):
        return
    _assert_transition(booking.status, BookingStatus.EXPIRED)
    show_seat_ids = [bs.show_seat_id for bs in booking.seats]
    await hold_service.release_hold(session, booking, "expired")
    await waitlist_service.try_offer_freed_seats(session, booking.show_id, show_seat_ids)


async def cancel_booking(session: AsyncSession, booking: Booking) -> Booking:
    if booking.status not in (BookingStatus.HELD, BookingStatus.PAYMENT_PENDING, BookingStatus.CONFIRMED):
        raise InvalidTransitionError(f"Cannot cancel a booking in status {booking.status}")

    if booking.status == BookingStatus.CONFIRMED:
        show_seat_ids = [bs.show_seat_id for bs in booking.seats]
        await session.execute(
            text(
                "UPDATE show_seats SET status = 'FREE', held_by_booking_id = NULL, "
                "hold_expires_at = NULL, version = version + 1 WHERE id = ANY(:ids)"
            ),
            {"ids": [str(i) for i in show_seat_ids]},
        )
        booking.status = BookingStatus.CANCELLED
        await outbox_service.emit(
            session, "booking", str(booking.id), "booking.cancelled",
            {"booking_id": str(booking.id), "show_id": str(booking.show_id), "seat_ids": [str(s) for s in show_seat_ids]},
        )
        await waitlist_service.try_offer_freed_seats(session, booking.show_id, show_seat_ids)
    else:
        _assert_transition(booking.status, BookingStatus.CANCELLED)
        show_seat_ids = [bs.show_seat_id for bs in booking.seats]
        await hold_service.release_hold(session, booking, "cancelled")
        await waitlist_service.try_offer_freed_seats(session, booking.show_id, show_seat_ids)

    await session.commit()
    return booking
