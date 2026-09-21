from app.models import OutboxEvent
from sqlalchemy.ext.asyncio import AsyncSession


async def emit(session: AsyncSession, aggregate_type: str, aggregate_id: str, event_type: str, payload: dict) -> None:
    """Writes an outbox row in the CALLER's transaction — must be called before commit
    so the state change and the event are atomic. The outbox worker publishes it later."""
    session.add(
        OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            event_type=event_type,
            payload=payload,
        )
    )
