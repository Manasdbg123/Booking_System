import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db import get_session
from app.schemas import EventOut, SeatMapOut, ShowOut
from app.services import catalog_service

router = APIRouter(prefix="/api", tags=["catalog"])
_optional_bearer = HTTPBearer(auto_error=False)


@router.get("/events", response_model=list[EventOut])
async def list_events(session: AsyncSession = Depends(get_session)):
    return await catalog_service.list_events(session)


@router.get("/events/{event_id}")
async def get_event(event_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    event = await catalog_service.get_event(session, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "poster_url": event.poster_url,
        "venue": event.venue,
        "shows": [ShowOut.model_validate(s) for s in event.shows],
    }


@router.get("/shows/{show_id}/seatmap", response_model=SeatMapOut)
async def get_seat_map(
    show_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    creds: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
):
    viewer_id = None
    if creds:
        payload = decode_access_token(creds.credentials)
        if payload:
            viewer_id = uuid.UUID(payload["sub"])

    data = await catalog_service.get_seat_map(session, show_id, viewer_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Show not found")
    return data
