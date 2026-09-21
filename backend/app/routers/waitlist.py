from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User, WaitlistEntry
from app.schemas import WaitlistJoinRequest, WaitlistOut
from app.services import waitlist_service

router = APIRouter(prefix="/api/waitlist", tags=["waitlist"])


@router.post("/join", response_model=WaitlistOut)
async def join(body: WaitlistJoinRequest, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    entry = await waitlist_service.join_waitlist(session, user.id, body.show_id, body.section_id)
    return WaitlistOut.model_validate(entry, from_attributes=True)


@router.get("/mine", response_model=list[WaitlistOut])
async def mine(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(WaitlistEntry).where(WaitlistEntry.user_id == user.id))).scalars().all()
    return [WaitlistOut.model_validate(r, from_attributes=True) for r in rows]
