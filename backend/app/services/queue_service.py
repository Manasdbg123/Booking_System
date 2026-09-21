"""Virtual waiting room for hot shows. Users get a queue position and are
admitted in batches with a signed, time-limited admission token that the
booking endpoints require for is_hot shows.

Position assignment is a soft FIFO (approximate under heavy concurrent
joins — two users can occasionally get adjacent positions swapped by a race
on the MAX(position)+1 read). That's acceptable here: unlike seat holds,
queue order is a UX fairness nicety, not a correctness guarantee that must
be airtight under test. Admission batching itself (who gets in) is exact,
driven by a single UPDATE ordered by position.
"""

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import QueueStatus, QueueTicket, Show


async def join_queue(session: AsyncSession, user_id: uuid.UUID, show_id: uuid.UUID) -> QueueTicket:
    show = await session.get(Show, show_id)
    existing = (
        await session.execute(
            select(QueueTicket).where(QueueTicket.show_id == show_id, QueueTicket.user_id == user_id, QueueTicket.status == QueueStatus.WAITING)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    if not show or not show.is_hot:
        # not a hot show — admit immediately
        ticket = QueueTicket(
            show_id=show_id, user_id=user_id, token=_make_token(show_id, user_id), position=0,
            status=QueueStatus.ADMITTED, admitted_at=datetime.now(timezone.utc),
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return ticket

    pos_row = await session.execute(
        text("SELECT COALESCE(MAX(position), 0) + 1 FROM queue_tickets WHERE show_id = :show_id"),
        {"show_id": str(show_id)},
    )
    position = pos_row.scalar_one()
    ticket = QueueTicket(show_id=show_id, user_id=user_id, token="", position=position, status=QueueStatus.WAITING)
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


def _make_token(show_id: uuid.UUID, user_id: uuid.UUID) -> str:
    payload = {
        "show_id": str(show_id),
        "user_id": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "typ": "admission",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_admission_token(token: str, show_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except Exception:
        return False
    return payload.get("typ") == "admission" and payload.get("show_id") == str(show_id) and payload.get("user_id") == str(user_id)


async def get_status(session: AsyncSession, ticket: QueueTicket) -> dict:
    if ticket.status == QueueStatus.ADMITTED:
        return {"ticket_id": ticket.id, "position": 0, "status": "ADMITTED", "admission_token": ticket.token, "estimated_wait_seconds": 0}

    ahead_row = await session.execute(
        text(
            "SELECT COUNT(*) FROM queue_tickets WHERE show_id = :show_id AND status = 'WAITING' AND position < :position"
        ),
        {"show_id": str(ticket.show_id), "position": ticket.position},
    )
    ahead = ahead_row.scalar_one()
    batches_needed = ahead // max(settings.queue_admission_rate_per_batch, 1)
    eta = int(batches_needed * settings.queue_batch_interval_seconds)
    return {"ticket_id": ticket.id, "position": ahead + 1, "status": "WAITING", "admission_token": None, "estimated_wait_seconds": eta}


async def admit_next_batch(session: AsyncSession) -> int:
    """Called by the worker on a tick. Admits up to admission_rate WAITING
    tickets per hot show, oldest position first."""
    hot_shows = (await session.execute(select(Show.id).where(Show.is_hot == True))).scalars().all()  # noqa: E712
    total_admitted = 0
    for show_id in hot_shows:
        tickets = (
            await session.execute(
                select(QueueTicket)
                .where(QueueTicket.show_id == show_id, QueueTicket.status == QueueStatus.WAITING)
                .order_by(QueueTicket.position)
                .limit(settings.queue_admission_rate_per_batch)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for ticket in tickets:
            ticket.status = QueueStatus.ADMITTED
            ticket.admitted_at = datetime.now(timezone.utc)
            ticket.token = _make_token(ticket.show_id, ticket.user_id)
            total_admitted += 1
    if total_admitted:
        await session.commit()
    return total_admitted
