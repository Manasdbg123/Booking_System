import groq
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import check_rate_limit
from app.db import get_session
from app.deps import get_current_user
from app.models import ChatMessage, ChatRole, ChatSession, User
from app.schemas import ChatMessageOut, ChatRequest, ChatResponse, ChatSessionOut, ToolCallOut
from app.services.ai import agent_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    allowed = await check_rate_limit(f"rl:ai:{user.id}", settings.ai_rate_limit_per_user_per_minute, settings.ai_rate_limit_per_user_per_minute)
    if not allowed:
        raise HTTPException(status_code=429, detail="AI assistant rate limit exceeded, try again shortly")

    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail="AI assistant is not configured (missing GROQ_API_KEY)")

    try:
        result = await agent_service.run_chat_turn(session, user.id, body.message, body.session_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except groq.RateLimitError:
        raise HTTPException(status_code=429, detail="The AI assistant's model provider is rate-limited right now, try again shortly")
    except groq.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"AI assistant's model provider returned an error: {e.message}")

    return ChatResponse(
        session_id=result.session_id,
        reply=result.reply,
        tool_calls=[ToolCallOut(**tc) for tc in result.tool_calls],
    )


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc()).limit(50)
        )
    ).scalars().all()
    return rows


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def session_messages(
    session_id,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None or chat_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.role.in_([ChatRole.USER, ChatRole.ASSISTANT]))
            .order_by(ChatMessage.created_at)
        )
    ).scalars().all()
    return [ChatMessageOut(role=r.role.value, content=r.content, created_at=r.created_at) for r in rows if r.content]
