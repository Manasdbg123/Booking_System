"""AI booking-assistant orchestration: the tool-calling loop, persistence,
and the safety net around it.

Architecture (see docs/ai-agent.md):

    User message
        -> load/create ChatSession + history
        -> Groq chat-completions API (OpenAI-compatible) with tool schemas
           (app/services/ai/tools.py, adapted to OpenAI function format)
        -> model emits tool_calls
        -> execute_tool() runs the REAL backend service (never raw SQL)
        -> tool results fed back as role="tool" messages
        -> repeat until the model returns plain text, or the iteration cap hits
        -> persist every turn; audit-log every tool call

The model never talks to the database. It talks to a fixed set of tools,
each of which is a thin, ownership-checked wrapper around an existing
service function — the same code path the REST API uses.

Targets Groq's OpenAI-compatible chat-completions API (tool_calls /
role="tool" messages). tools.py itself is provider-agnostic (plain
name/description/input_schema); `_to_openai_tools` is the only adapter
needed to switch providers.
"""

import json
import uuid
from dataclasses import dataclass

import groq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import get_logger
from app.models import AuditLog, ChatMessage, ChatRole, ChatSession
from app.services.ai.tools import TOOL_SCHEMAS, IRREVERSIBLE_TOOLS, ToolContext, ToolError, execute_tool

logger = get_logger("ai_agent")

SYSTEM_PROMPT = """You are the SeatRush booking assistant. SeatRush sells seats for live \
shows/events (concerts, plays, sports) — not hotels or vehicles.

Rules you must follow:
1. Always use tools to get real data (availability, prices, booking status, policies). \
Never invent seat availability, prices, or policy answers.
2. For policy questions (cancellation, refunds, rules), call search_policies and answer \
only from what it returns. If it returns nothing relevant, say you don't know and suggest \
contacting support.
3. create_booking_hold, confirm_and_pay, and cancel_booking are irreversible-ish actions. \
Only call them after the user has clearly said yes to the specific seats/booking you \
described to them. Never call them speculatively "to see what happens".
4. A hold is not a purchase. Be explicit with the user about the difference, and that a \
hold expires if not paid within the platform's hold window.
5. You can only see and act on the current user's own bookings — never claim to access \
anyone else's.
6. Keep replies concise and concrete: state exact seats, prices, and next steps.
"""


@dataclass
class AgentTurnResult:
    session_id: uuid.UUID
    reply: str
    tool_calls: list[dict]


def _client() -> groq.AsyncGroq:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    return groq.AsyncGroq(api_key=settings.groq_api_key)


def _to_openai_tools() -> list[dict]:
    return [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in TOOL_SCHEMAS
    ]


async def _get_or_create_session(session: AsyncSession, user_id: uuid.UUID, chat_session_id: uuid.UUID | None) -> ChatSession:
    if chat_session_id is not None:
        chat_session = await session.get(ChatSession, chat_session_id)
        if chat_session is not None and chat_session.user_id == user_id:
            return chat_session
    chat_session = ChatSession(user_id=user_id)
    session.add(chat_session)
    await session.flush()
    return chat_session


def _truncate_history(messages: list[dict], max_messages: int) -> list[dict]:
    """Keeps whole conversation turns (a user message plus everything that
    followed it) rather than an arbitrary message-count cutoff, so we never
    strip an assistant tool_calls message while keeping its role="tool"
    result — the API rejects that pairing. Bounds token usage per request:
    without this, a long-running session resends every past tool result
    (e.g. full search_shows payloads) on every turn, which on a
    rate-limited free-tier model budget (Groq's TPM cap) turns an ordinary
    multi-turn conversation into a 413 after a handful of turns."""
    if len(messages) <= max_messages:
        return messages
    turn_starts = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if not turn_starts:
        return messages[-max_messages:]
    cut = turn_starts[-1]
    for start in turn_starts:
        if len(messages) - start <= max_messages:
            cut = start
            break
    return messages[cut:]


async def _load_history(session: AsyncSession, chat_session_id: uuid.UUID) -> list[dict]:
    """Cross-turn context is plain user/assistant TEXT only — raw tool_calls
    and tool-result messages from past turns are never replayed.

    Why: a past turn's tool_calls/tool_result plumbing is only valid to
    resend if the exact same request shape round-trips through the
    provider's template unchanged. In practice this is brittle across
    OpenAI-"compatible" providers: Groq's gpt-oss "harmony" template
    rejected a perfectly well-formed replayed tool_calls history with
    'Tools should have a name!' — a template-internal validation, not a
    malformed request on our side. Rather than chase one provider's
    template quirks, we never replay tool plumbing at all: each turn's
    tool round-trip is self-contained (built fresh in run_chat_turn) and
    discarded once the assistant's final text reply is produced. That
    reply already summarizes whatever the tools found, so the model
    doesn't lose the substance — only the raw call/response objects,
    which it doesn't need again once summarized in its own words.
    """
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat_session_id, ChatMessage.role.in_([ChatRole.USER, ChatRole.ASSISTANT]))
            .order_by(ChatMessage.created_at)
        )
    ).scalars().all()

    return [{"role": "user" if row.role == ChatRole.USER else "assistant", "content": row.content} for row in rows if row.content]


async def _audit_tool_call(session: AsyncSession, user_id: uuid.UUID, chat_session_id: uuid.UUID, tool_name: str, args: dict, outcome: str) -> None:
    session.add(
        AuditLog(
            actor=f"ai_agent:{user_id}",
            action=f"tool_call:{tool_name}",
            entity="chat_session",
            entity_id=str(chat_session_id),
            reasoning=f"AI agent invoked tool {tool_name} with args {args}"[:2000],
            outcome=outcome[:100],
            extra={"tool": tool_name, "args": {k: str(v) for k, v in args.items()}},
        )
    )


async def run_chat_turn(
    session: AsyncSession,
    user_id: uuid.UUID,
    user_message: str,
    chat_session_id: uuid.UUID | None = None,
) -> AgentTurnResult:
    chat_session = await _get_or_create_session(session, user_id, chat_session_id)
    if chat_session.title == "New conversation" and user_message.strip():
        chat_session.title = user_message.strip()[:80]

    history = _truncate_history(await _load_history(session, chat_session.id), settings.ai_history_max_messages)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_message}]

    session.add(ChatMessage(session_id=chat_session.id, role=ChatRole.USER, content=user_message[:8000]))
    await session.flush()

    client = _client()
    tools = _to_openai_tools()
    tool_ctx = ToolContext(session=session, user_id=user_id)
    tool_calls_log: list[dict] = []

    final_text = ""
    for _ in range(settings.ai_max_tool_iterations):
        response = await client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=1024,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        assistant_tool_calls = [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls
        ]
        assistant_message = {"role": "assistant", "content": message.content}
        if assistant_tool_calls:
            assistant_message["tool_calls"] = assistant_tool_calls
        messages.append(assistant_message)

        final_text = (message.content or "").strip() or final_text

        session.add(
            ChatMessage(
                session_id=chat_session.id,
                role=ChatRole.ASSISTANT,
                content=(message.content or "")[:8000],
                tool_blocks={"tool_calls": assistant_tool_calls} if assistant_tool_calls else None,
            )
        )

        if not tool_calls:
            break

        tool_result_messages = []
        for tc in tool_calls:
            outcome = "ok"
            result: dict = {}
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                outcome = "error: malformed arguments"
                args = {}
                content = "Error: arguments were not valid JSON"
            else:
                try:
                    result = await execute_tool(tool_ctx, tc.function.name, args)
                    content = _to_tool_result_text(result)
                except ToolError as e:
                    outcome = f"error: {e}"
                    content = f"Error: {e}"
                except Exception:
                    logger.exception("ai_tool_unexpected_error", tool=tc.function.name)
                    outcome = "error: internal"
                    content = "Error: the tool failed unexpectedly. Do not retry the same call blindly."

            if tc.function.name in IRREVERSIBLE_TOOLS or outcome != "ok":
                await _audit_tool_call(session, user_id, chat_session.id, tc.function.name, args, outcome)

            tool_calls_log.append({"name": tc.function.name, "input": args, "outcome": outcome, "result": result})
            tool_result_messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

        messages.extend(tool_result_messages)
        session.add(
            ChatMessage(session_id=chat_session.id, role=ChatRole.TOOL, content="[tool results]", tool_blocks={"messages": tool_result_messages})
        )

    if not final_text:
        final_text = "I wasn't able to finish that request within my tool-call budget — could you rephrase or narrow it down?"

    await session.commit()
    return AgentTurnResult(session_id=chat_session.id, reply=final_text, tool_calls=tool_calls_log)


def _to_tool_result_text(result: dict) -> str:
    return json.dumps(result, default=str)
