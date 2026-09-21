"""Sweeps expired holds/payment-pending bookings and stale waitlist offers.

Crash/Redis-loss resilience: this worker reads its work list from Postgres
(bookings.expires_at), not Redis. Redis is only used as a hint elsewhere
(nowhere in this sweep, in fact) — so if the worker crashes mid-batch, or
Redis is flushed entirely, the next tick (from this or another worker
instance) picks up exactly where it left off by re-querying Postgres for
still-expired rows. A seat can never get stuck HELD forever and can never
be double-booked by this process, because every state change here still
goes through the same conditional-UPDATE path used everywhere else.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.logging import get_logger
from app.core.metrics import holds_expired_total
from app.db import SessionLocal
from app.models import Booking, BookingStatus
from app.services import booking_service, queue_service, waitlist_service

logger = get_logger("expiry_worker")


async def sweep_once() -> int:
    now = datetime.now(timezone.utc)
    expired_count = 0

    async with SessionLocal() as session:
        candidate_ids = (
            await session.execute(
                select(Booking.id)
                .where(Booking.status.in_([BookingStatus.HELD, BookingStatus.PAYMENT_PENDING]), Booking.expires_at < now)
                .limit(500)
            )
        ).scalars().all()

    # Each booking is locked AND processed within the same transaction, so the
    # lock actually protects against a second worker instance racing us —
    # SKIP LOCKED means it just moves on to the next candidate instead of
    # blocking or double-processing.
    for booking_id in candidate_ids:
        async with SessionLocal() as session:
            locked = (
                await session.execute(
                    select(Booking.id).where(Booking.id == booking_id).with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if locked is None:
                continue  # another worker instance is already handling this one

            booking = await session.get(Booking, booking_id, options=[selectinload(Booking.seats)])
            if booking is None or booking.expires_at is None or booking.expires_at >= datetime.now(timezone.utc):
                continue
            if booking.status not in (BookingStatus.HELD, BookingStatus.PAYMENT_PENDING):
                continue
            await booking_service.expire_booking(session, booking)
            await session.commit()
            expired_count += 1
            holds_expired_total.inc()

    async with SessionLocal() as session:
        stale_offers = await waitlist_service.expire_stale_offers(session)
        await session.commit()

    async with SessionLocal() as session:
        admitted = await queue_service.admit_next_batch(session)

    if expired_count or stale_offers or admitted:
        logger.info("sweep", expired=expired_count, stale_offers=stale_offers, admitted=admitted)

    return expired_count


async def run_forever() -> None:
    logger.info("expiry_worker_started", interval=settings.expiry_worker_interval_seconds)
    while True:
        try:
            await sweep_once()
        except Exception:
            logger.exception("sweep_failed")
        await asyncio.sleep(settings.expiry_worker_interval_seconds)
