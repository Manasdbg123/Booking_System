import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_admin
from app.models import AuditLog, Booking, BookingStatus, OutboxEvent, QueueStatus, QueueTicket, SeatStatus, ShowSeat

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/metrics")
async def metrics(session: AsyncSession = Depends(get_session)):
    active_holds = (
        await session.execute(select(func.count()).select_from(ShowSeat).where(ShowSeat.status == SeatStatus.HELD))
    ).scalar_one()
    sales_last_hour = (
        await session.execute(
            select(func.count()).select_from(Booking).where(
                Booking.status == BookingStatus.CONFIRMED, Booking.updated_at > func.now() - text("interval '1 hour'")
            )
        )
    ).scalar_one()
    queue_depth = (
        await session.execute(select(func.count()).select_from(QueueTicket).where(QueueTicket.status == QueueStatus.WAITING))
    ).scalar_one()
    outbox_backlog = (
        await session.execute(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.published_at.is_(None)))
    ).scalar_one()
    return {
        "active_holds": active_holds,
        "sales_last_hour": sales_last_hour,
        "queue_depth": queue_depth,
        "outbox_backlog": outbox_backlog,
    }


@router.get("/shows/{show_id}/heatmap")
async def seat_heatmap(show_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(ShowSeat.status, func.count()).where(ShowSeat.show_id == show_id).group_by(ShowSeat.status)
        )
    ).all()
    return {status.value: count for status, count in rows}


@router.get("/audit-log")
async def audit_log(session: AsyncSession = Depends(get_session), limit: int = 100):
    rows = (await session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))).scalars().all()
    return rows


@router.get("/bookings/recent")
async def recent_bookings(session: AsyncSession = Depends(get_session), limit: int = 50):
    rows = (await session.execute(select(Booking).order_by(Booking.updated_at.desc()).limit(limit))).scalars().all()
    return rows


@router.post("/shows/{show_id}/mark-hot")
async def mark_hot(show_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    from app.models import Show

    show = await session.get(Show, show_id)
    if show:
        show.is_hot = True
        await session.commit()
    return {"ok": True}
