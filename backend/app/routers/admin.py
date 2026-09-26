import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_admin
from app.models import AuditLog, Booking, BookingStatus, OutboxEvent, PaymentStatus, Payment, QueueStatus, QueueTicket, SeatStatus, ShowSeat, User

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
async def audit_log(session: AsyncSession = Depends(get_session), limit: int = 100, actor_prefix: str | None = None):
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if actor_prefix:
        query = select(AuditLog).where(AuditLog.actor.like(f"{actor_prefix}%")).order_by(AuditLog.created_at.desc()).limit(limit)
    rows = (await session.execute(query)).scalars().all()
    return rows


@router.get("/ai-activity")
async def ai_activity(session: AsyncSession = Depends(get_session), limit: int = 100):
    """AI tool-call audit trail: every irreversible action (and every failed
    tool call) the AI agent has taken, across all users, for admin review."""
    rows = (
        await session.execute(
            select(AuditLog).where(AuditLog.actor.like("ai_agent:%")).order_by(AuditLog.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return rows


@router.get("/analytics")
async def analytics(session: AsyncSession = Depends(get_session)):
    total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    total_bookings = (await session.execute(select(func.count()).select_from(Booking))).scalar_one()
    revenue = (
        await session.execute(select(func.coalesce(func.sum(Booking.total_amount), 0)).where(Booking.status == BookingStatus.CONFIRMED))
    ).scalar_one()
    confirmed = (
        await session.execute(select(func.count()).select_from(Booking).where(Booking.status == BookingStatus.CONFIRMED))
    ).scalar_one()
    cancelled = (
        await session.execute(select(func.count()).select_from(Booking).where(Booking.status == BookingStatus.CANCELLED))
    ).scalar_one()
    cancellation_rate_pct = round((cancelled / total_bookings) * 100, 2) if total_bookings else 0.0
    failed_payments = (
        await session.execute(select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.FAILED))
    ).scalar_one()
    active_inventory = (
        await session.execute(select(func.count()).select_from(ShowSeat).where(ShowSeat.status == SeatStatus.FREE))
    ).scalar_one()

    booking_volume_by_day = (
        await session.execute(
            text(
                "SELECT date_trunc('day', created_at) AS day, count(*) FROM bookings "
                "WHERE created_at > now() - interval '14 days' GROUP BY 1 ORDER BY 1"
            )
        )
    ).all()

    return {
        "total_users": total_users,
        "total_bookings": total_bookings,
        "revenue": str(revenue),
        "confirmed_bookings": confirmed,
        "cancellation_rate_pct": cancellation_rate_pct,
        "failed_payments": failed_payments,
        "active_inventory": active_inventory,
        "booking_volume_by_day": [{"day": day.isoformat(), "count": count} for day, count in booking_volume_by_day],
    }


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
