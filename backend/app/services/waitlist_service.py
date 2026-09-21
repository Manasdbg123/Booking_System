"""Waitlist: FIFO per (show, section). When a seat frees up, the earliest
WAITING entry is offered it exactly once via a time-limited hold.

Exactly-once + FIFO is guaranteed by claiming the next entry with:
    UPDATE waitlist_entries SET status='OFFERED', ...
    WHERE id = (SELECT id FROM waitlist_entries WHERE ... status='WAITING'
                ORDER BY position FOR UPDATE SKIP LOCKED LIMIT 1)
SKIP LOCKED means two concurrent seat-releases racing to offer a seat never
pick the same waiting entry twice, and ORDER BY position enforces fairness.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Booking, BookingSeat, BookingStatus, Seat, ShowSeat, WaitlistEntry, WaitlistStatus
from app.services import outbox_service


async def join_waitlist(session: AsyncSession, user_id: uuid.UUID, show_id: uuid.UUID, section_id: uuid.UUID) -> WaitlistEntry:
    count_row = await session.execute(
        text(
            "SELECT COUNT(*) FROM waitlist_entries WHERE show_id=:show_id AND section_id=:section_id AND status='WAITING'"
        ),
        {"show_id": str(show_id), "section_id": str(section_id)},
    )
    position = count_row.scalar_one() + 1
    entry = WaitlistEntry(show_id=show_id, section_id=section_id, user_id=user_id, position=position, status=WaitlistStatus.WAITING)
    session.add(entry)
    await outbox_service.emit(
        session, "waitlist", str(user_id), "waitlist.joined",
        {"show_id": str(show_id), "section_id": str(section_id), "position": position},
    )
    await session.commit()
    await session.refresh(entry)
    return entry


async def try_offer_freed_seats(session: AsyncSession, show_id: uuid.UUID, freed_show_seat_ids: list[uuid.UUID]) -> None:
    """Call right after seats are flipped back to FREE. For each seat, tries
    to hand it to the next waiter in that seat's section."""
    for show_seat_id in freed_show_seat_ids:
        row = (
            await session.execute(
                select(ShowSeat, Seat.section_id)
                .join(Seat, Seat.id == ShowSeat.seat_id)
                .where(ShowSeat.id == show_seat_id)
            )
        ).first()
        if row is None:
            continue
        show_seat, section_id = row
        if show_seat.status != "FREE":
            continue
        await _offer_seat_to_next_waiter(session, show_id, section_id, show_seat)


async def _offer_seat_to_next_waiter(session: AsyncSession, show_id: uuid.UUID, section_id: uuid.UUID, show_seat: ShowSeat) -> None:
    result = await session.execute(
        text(
            """
            UPDATE waitlist_entries
            SET status = 'OFFERED', offered_show_seat_id = :show_seat_id, offer_expires_at = :expires_at
            WHERE id = (
                SELECT id FROM waitlist_entries
                WHERE show_id = :show_id AND section_id = :section_id AND status = 'WAITING'
                ORDER BY position ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, user_id
            """
        ),
        {
            "show_seat_id": str(show_seat.id),
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=settings.waitlist_offer_ttl_seconds),
            "show_id": str(show_id),
            "section_id": str(section_id),
        },
    )
    claimed = result.first()
    if claimed is None:
        return  # nobody waiting for this section

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.waitlist_offer_ttl_seconds)
    hold_result = await session.execute(
        text("UPDATE show_seats SET status='HELD', hold_expires_at=:exp, version = version + 1 WHERE id=:id AND status='FREE'"),
        {"exp": expires_at, "id": str(show_seat.id)},
    )
    if hold_result.rowcount == 0:
        # Extremely unlikely (seat taken between our earlier check and now within
        # the same transaction) — put the entry back to WAITING at the front.
        await session.execute(
            text("UPDATE waitlist_entries SET status='WAITING', offered_show_seat_id=NULL, offer_expires_at=NULL WHERE id=:id"),
            {"id": claimed.id},
        )
        return

    booking = Booking(
        user_id=claimed.user_id,
        show_id=show_id,
        status=BookingStatus.HELD,
        expires_at=expires_at,
        total_amount=show_seat.price,
    )
    session.add(booking)
    await session.flush()

    await session.execute(
        text("UPDATE show_seats SET held_by_booking_id=:bid WHERE id=:id"),
        {"bid": str(booking.id), "id": str(show_seat.id)},
    )
    session.add(BookingSeat(booking_id=booking.id, show_seat_id=show_seat.id, price=show_seat.price))

    await outbox_service.emit(
        session, "waitlist", str(claimed.id), "waitlist.offered",
        {"waitlist_entry_id": str(claimed.id), "user_id": str(claimed.user_id), "booking_id": str(booking.id),
         "show_id": str(show_id), "show_seat_id": str(show_seat.id), "expires_at": expires_at.isoformat()},
    )


async def mark_claimed_if_applicable(session: AsyncSession, booking: Booking) -> None:
    show_seat_ids = [bs.show_seat_id for bs in booking.seats]
    if not show_seat_ids:
        return
    await session.execute(
        text(
            "UPDATE waitlist_entries SET status='CLAIMED' "
            "WHERE offered_show_seat_id = ANY(:ids) AND status='OFFERED'"
        ),
        {"ids": [str(i) for i in show_seat_ids]},
    )


async def expire_stale_offers(session: AsyncSession) -> int:
    """Called by the expiry worker. Any OFFERED entry past its TTL is marked
    EXPIRED; its booking (if still HELD) is released via the normal hold-expiry
    path, which in turn re-triggers try_offer_freed_seats for the next waiter."""
    now = datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(WaitlistEntry).where(WaitlistEntry.status == WaitlistStatus.OFFERED, WaitlistEntry.offer_expires_at < now)
        )
    ).scalars().all()
    for entry in rows:
        entry.status = WaitlistStatus.EXPIRED
    return len(rows)
