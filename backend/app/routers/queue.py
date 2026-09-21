from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import QueueTicket, User
from app.schemas import QueueJoinRequest, QueueStatusOut
from app.services import queue_service

router = APIRouter(prefix="/api/queue", tags=["queue"])


@router.post("/join", response_model=QueueStatusOut)
async def join(body: QueueJoinRequest, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ticket = await queue_service.join_queue(session, user.id, body.show_id)
    status = await queue_service.get_status(session, ticket)
    return QueueStatusOut(**status)


@router.get("/status/{ticket_id}", response_model=QueueStatusOut)
async def status(ticket_id, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ticket = await session.get(QueueTicket, ticket_id)
    if ticket is None or ticket.user_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")
    result = await queue_service.get_status(session, ticket)
    return QueueStatusOut(**result)
