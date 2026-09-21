"""Seat holds: the core correctness-critical path.

Locking strategy (see docs/design.md for the full comparison):
- Each seat's row in show_seats carries status FREE/HELD/SOLD.
- We acquire a hold with a single conditional UPDATE per seat:
    UPDATE show_seats SET status='HELD', ... WHERE id = :id AND status = 'FREE'
  The WHERE clause is the concurrency control: Postgres serializes concurrent
  UPDATEs to the same row, and only one writer's predicate matches. No
  explicit SELECT FOR UPDATE is needed because there is no read-then-write
  gap — the check and the write are the same atomic statement.
- For a multi-seat hold, all seats are updated inside ONE transaction, in a
  DETERMINISTIC order (sorted by show_seats.id). Every caller that might
  contend for overlapping seat sets therefore acquires locks in the same
  order, so the database can never deadlock two holds against each other.
- If any seat in the request is not FREE, the whole transaction is rolled
  back — nothing is partially held (requirement: atomic multi-seat holds).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.metrics import hold_conflicts_total, holds_created_total
from app.models import Booking, BookingSeat, BookingStatus, Show, ShowSeat
from app.services import outbox_service, pricing


class SeatsUnavailableError(Exception):
    def __init__(self, unavailable_seat_ids: list[uuid.UUID]):
        self.unavailable_seat_ids = unavailable_seat_ids
        super().__init__(f"Seats unavailable: {unavailable_seat_ids}")


class ShowNotFoundError(Exception):
    pass


async def create_hold(
    session: AsyncSession,
    user_id: uuid.UUID,
    show_id: uuid.UUID,
    seat_ids: list[uuid.UUID],
) -> Booking:
    show = await session.get(Show, show_id)
    if show is None:
        raise ShowNotFoundError()

    # Load the show_seats rows for the requested seats, sorted by id for
    # deterministic lock ordering across all concurrent callers.
    rows = (
        await session.execute(
            select(ShowSeat)
            .where(ShowSeat.show_id == show_id, ShowSeat.seat_id.in_(seat_ids))
            .order_by(ShowSeat.id)
        )
    ).scalars().all()

    if len(rows) != len(set(seat_ids)):
        found_seat_ids = {r.seat_id for r in rows}
        missing = [s for s in seat_ids if s not in found_seat_ids]
        raise SeatsUnavailableError(missing)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.hold_ttl_seconds)

    booking = Booking(
        user_id=user_id,
        show_id=show_id,
        status=BookingStatus.HELD,
        expires_at=expires_at,
        total_amount=0,
    )
    session.add(booking)
    await session.flush()  # assigns booking.id

    unavailable: list[uuid.UUID] = []
    acquired_prices = []
    for row in rows:
        result = await session.execute(
            text(
                """
                UPDATE show_seats
                SET status = 'HELD', held_by_booking_id = :booking_id,
                    hold_expires_at = :expires_at, version = version + 1
                WHERE id = :show_seat_id AND status = 'FREE'
                """
            ),
            {"booking_id": str(booking.id), "expires_at": expires_at, "show_seat_id": str(row.id)},
        )
        if result.rowcount == 0:
            unavailable.append(row.seat_id)
        else:
            session.add(BookingSeat(booking_id=booking.id, show_seat_id=row.id, price=row.price))
            acquired_prices.append(row.price)

    if unavailable:
        hold_conflicts_total.inc()
        await session.rollback()
        raise SeatsUnavailableError(unavailable)

    booking.total_amount = pricing.total_for_seats(acquired_prices)
    await outbox_service.emit(
        session,
        "booking",
        str(booking.id),
        "booking.held",
        {
            "booking_id": str(booking.id),
            "show_id": str(show_id),
            "seat_ids": [str(s) for s in seat_ids],
            "expires_at": expires_at.isoformat(),
        },
    )
    await session.commit()
    holds_created_total.inc()
    return booking


async def free_held_seats(session: AsyncSession, booking: Booking) -> list[uuid.UUID]:
    """Flips every seat this booking still HELDs back to FREE. Does not touch
    booking.status — callers decide the target status per the state machine."""
    show_seat_ids = [bs.show_seat_id for bs in booking.seats]
    if show_seat_ids:
        await session.execute(
            text(
                """
                UPDATE show_seats
                SET status = 'FREE', held_by_booking_id = NULL, hold_expires_at = NULL, version = version + 1
                WHERE id = ANY(:ids) AND held_by_booking_id = :booking_id
                """
            ),
            {"ids": [str(i) for i in show_seat_ids], "booking_id": str(booking.id)},
        )
    return show_seat_ids


async def release_hold(session: AsyncSession, booking: Booking, reason: str) -> None:
    """Releases every HELD seat on a booking back to FREE and marks the booking
    terminal (EXPIRED or CANCELLED). Used by expiry and user-cancellation paths."""
    show_seat_ids = await free_held_seats(session, booking)
    new_status = BookingStatus.EXPIRED if reason == "expired" else BookingStatus.CANCELLED
    booking.status = new_status
    await outbox_service.emit(
        session,
        "booking",
        str(booking.id),
        f"booking.{reason}",
        {"booking_id": str(booking.id), "show_id": str(booking.show_id), "seat_ids": [str(s) for s in show_seat_ids]},
    )
