"""Drains outbox_events into Redis pub/sub for the realtime WebSocket channel.

This is the second half of the outbox pattern: the state change (seat status,
booking status) and the outbox row are written atomically in one Postgres
transaction by the service layer. This worker's only job is "at least once"
delivery of that row to Redis — if it crashes after publishing but before
marking published_at, the row is republished on the next tick, which is
safe because every event the frontend renders (seat map, queue position) is
a snapshot-safe re-render, not an incremental counter.
"""

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.core.logging import get_logger
from app.core.metrics import outbox_backlog
from app.core.redis_client import get_redis
from app.db import SessionLocal
from app.models import OutboxEvent

logger = get_logger("outbox_worker")


async def drain_once() -> int:
    async with SessionLocal() as session:
        events = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).order_by(OutboxEvent.created_at).limit(500)
            )
        ).scalars().all()

        redis = get_redis()
        published = 0
        for event in events:
            channel = _channel_for(event)
            if channel:
                message = json.dumps(
                    {"type": event.event_type, "aggregate_type": event.aggregate_type, "aggregate_id": event.aggregate_id, "payload": event.payload}
                )
                await redis.publish(channel, message)
            event.published_at = datetime.now(timezone.utc)
            published += 1

        if published:
            await session.commit()

    async with SessionLocal() as session:
        remaining = (
            await session.execute(select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).limit(1))
        ).first()
        outbox_backlog.set(0 if remaining is None else 1)

    return published


def _channel_for(event: OutboxEvent) -> str | None:
    show_id = event.payload.get("show_id") if isinstance(event.payload, dict) else None
    if show_id:
        return f"show:{show_id}:events"
    return None


async def run_forever() -> None:
    logger.info("outbox_worker_started", interval=settings.outbox_worker_interval_seconds)
    while True:
        try:
            await drain_once()
        except Exception:
            logger.exception("drain_failed")
        await asyncio.sleep(settings.outbox_worker_interval_seconds)
