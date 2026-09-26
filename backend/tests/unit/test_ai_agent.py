"""AI agent tests.

The Groq client is mocked (no network, no API key needed) — what we're
testing is OUR code: tool ownership enforcement, the tool-calling loop
mechanics, audit logging, and RAG retrieval quality. All of it runs against
the real test Postgres via the same seeded_show/user fixtures the rest of
the suite uses, per this repo's stance that correctness must be proven
against the real engine, not a mock DB.
"""

import json
import types
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import AuditLog, User, UserRole
from app.services import hold_service
from app.services.ai import rag
from app.services.ai.agent_service import run_chat_turn
from app.services.ai.tools import ToolContext, ToolError, execute_tool


async def _make_user(tag: str):
    async with SessionLocal() as session:
        u = User(email=f"ai-{tag}-{uuid.uuid4().hex[:6]}@test.dev", password_hash=hash_password("x"), role=UserRole.USER)
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return u.id


# ---- tool ownership / correctness ----


@pytest.mark.asyncio
async def test_search_shows_filters_by_price_and_availability(db_session, seeded_show):
    ctx = ToolContext(session=db_session, user_id=uuid.uuid4())
    result = await execute_tool(ctx, "search_shows", {"max_price": 1000, "available_only": True})
    assert result["count"] >= 1
    assert all(float(e["from_price"]) <= 1000 for e in result["events"] if e["from_price"])


@pytest.mark.asyncio
async def test_check_availability_reports_section_counts(db_session, seeded_show):
    ctx = ToolContext(session=db_session, user_id=uuid.uuid4())
    result = await execute_tool(ctx, "check_availability", {"show_id": str(seeded_show["show"].id)})
    assert "General" in result["by_section"]
    assert result["by_section"]["General"]["free"] == 50


@pytest.mark.asyncio
async def test_create_booking_hold_then_cancel_round_trip(seeded_show):
    user_id = await _make_user("holder")
    seat = seeded_show["seats"][0]

    async with SessionLocal() as session:
        ctx = ToolContext(session=session, user_id=user_id)
        hold_result = await execute_tool(ctx, "create_booking_hold", {"show_id": str(seeded_show["show"].id), "seat_ids": [str(seat.id)]})
    assert hold_result["status"] == "HELD"

    async with SessionLocal() as session:
        ctx = ToolContext(session=session, user_id=user_id)
        cancel_result = await execute_tool(ctx, "cancel_booking", {"booking_id": hold_result["booking_id"]})
    assert cancel_result["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cannot_cancel_another_users_booking(seeded_show):
    owner_id = await _make_user("owner")
    attacker_id = await _make_user("attacker")
    seat = seeded_show["seats"][1]

    async with SessionLocal() as session:
        booking = await hold_service.create_hold(session, owner_id, seeded_show["show"].id, [seat.id])

    async with SessionLocal() as session:
        ctx = ToolContext(session=session, user_id=attacker_id)
        with pytest.raises(ToolError):
            await execute_tool(ctx, "cancel_booking", {"booking_id": str(booking.id)})

    async with SessionLocal() as session:
        ctx = ToolContext(session=session, user_id=attacker_id)
        with pytest.raises(ToolError):
            await execute_tool(ctx, "get_booking_details", {"booking_id": str(booking.id)})


@pytest.mark.asyncio
async def test_user_id_argument_is_ignored_because_schema_has_none():
    from app.services.ai.tools import TOOL_SCHEMAS

    for schema in TOOL_SCHEMAS:
        assert "user_id" not in schema["input_schema"].get("properties", {})


@pytest.mark.asyncio
async def test_invalid_booking_id_is_a_tool_error_not_a_crash(db_session):
    ctx = ToolContext(session=db_session, user_id=uuid.uuid4())
    with pytest.raises(ToolError):
        await execute_tool(ctx, "get_booking_details", {"booking_id": "not-a-uuid"})


# ---- RAG ----


def test_rag_retrieves_relevant_cancellation_passage():
    results = rag.retrieve("can I cancel a confirmed booking and get a refund")
    assert results
    assert any("cancel" in r["heading"].lower() or "refund" in r["doc"].lower() for r in results)


def test_rag_returns_nothing_for_unrelated_query():
    results = rag.retrieve("zzz completely unrelated gibberish qwerty")
    assert results == [] or all(r["score"] < 0.05 for r in results)


# ---- agent loop (Groq/OpenAI-compatible client mocked) ----


def _function_call(tool_id, name, args: dict):
    return types.SimpleNamespace(id=tool_id, function=types.SimpleNamespace(name=name, arguments=json.dumps(args)))


def _completion(content: str | None, tool_calls: list | None = None):
    message = types.SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _mock_client(responses):
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=AsyncMock(side_effect=responses))))


@pytest.mark.asyncio
async def test_agent_loop_calls_tool_then_returns_text(seeded_show):
    user_id = await _make_user("chatter")

    responses = [
        _completion(None, [_function_call("t1", "search_shows", {"available_only": True})]),
        _completion("I found a show for you."),
    ]
    mock_client = _mock_client(responses)

    async with SessionLocal() as session:
        with patch("app.services.ai.agent_service._client", return_value=mock_client), \
             patch("app.services.ai.agent_service.settings.groq_api_key", "fake-key-for-test"):
            result = await run_chat_turn(session, user_id, "find me a show")

    assert result.reply == "I found a show for you."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "search_shows"
    assert result.tool_calls[0]["outcome"] == "ok"


@pytest.mark.asyncio
async def test_irreversible_tool_call_is_audit_logged(seeded_show):
    user_id = await _make_user("payer")
    seat = seeded_show["seats"][2]
    show_id = str(seeded_show["show"].id)

    responses = [
        _completion(None, [_function_call("t1", "create_booking_hold", {"show_id": show_id, "seat_ids": [str(seat.id)]})]),
        _completion("Held it for you."),
    ]
    mock_client = _mock_client(responses)

    async with SessionLocal() as session:
        with patch("app.services.ai.agent_service._client", return_value=mock_client), \
             patch("app.services.ai.agent_service.settings.groq_api_key", "fake-key-for-test"):
            await run_chat_turn(session, user_id, "hold seat A1")

    async with SessionLocal() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(AuditLog).where(AuditLog.actor == f"ai_agent:{user_id}"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == "tool_call:create_booking_hold"


@pytest.mark.asyncio
async def test_cross_turn_history_never_replays_tool_calls(seeded_show):
    """Regression test for a real failure found against the live Groq API:
    resending a past turn's tool_calls/tool_result objects on the next turn
    got rejected by the model provider's chat template. Cross-turn context
    must be plain user/assistant text only."""
    user_id = await _make_user("historian")

    turn1_responses = [
        _completion(None, [_function_call("t1", "search_shows", {})]),
        _completion("Found some shows for you."),
    ]
    turn2_responses = [_completion("Sure, here's more detail.")]

    async with SessionLocal() as session:
        with patch("app.services.ai.agent_service._client", return_value=_mock_client(turn1_responses)), \
             patch("app.services.ai.agent_service.settings.groq_api_key", "fake-key-for-test"):
            first = await run_chat_turn(session, user_id, "find me a show")

    turn2_client = _mock_client(turn2_responses)
    async with SessionLocal() as session:
        with patch("app.services.ai.agent_service._client", return_value=turn2_client), \
             patch("app.services.ai.agent_service.settings.groq_api_key", "fake-key-for-test"):
            await run_chat_turn(session, user_id, "tell me more", first.session_id)

    sent_messages = turn2_client.chat.completions.create.await_args.kwargs["messages"]
    assert all(m["role"] in ("system", "user", "assistant") for m in sent_messages)
    assert all("tool_calls" not in m for m in sent_messages)
    assert not any(m["role"] == "tool" for m in sent_messages)


@pytest.mark.asyncio
async def test_agent_loop_stops_at_iteration_cap(seeded_show):
    user_id = await _make_user("looper")

    # Model calls a tool every turn, never emitting plain text.
    infinite_tool_call = _completion(None, [_function_call("t1", "search_shows", {})])
    mock_client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=AsyncMock(return_value=infinite_tool_call))))

    async with SessionLocal() as session:
        with patch("app.services.ai.agent_service._client", return_value=mock_client), \
             patch("app.services.ai.agent_service.settings.groq_api_key", "fake-key-for-test"), \
             patch("app.services.ai.agent_service.settings.ai_max_tool_iterations", 3):
            result = await run_chat_turn(session, user_id, "loop forever")

    assert mock_client.chat.completions.create.await_count == 3
    assert "budget" in result.reply.lower()
