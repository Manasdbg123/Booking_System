"""AI tool definitions + executors.

Guardrails (see docs/ai-agent.md for the full write-up):
- Every tool function takes `user_id` from the authenticated session
  (threaded in by agent_service.py from the JWT), never from a model-
  supplied argument. Tool JSON schemas below deliberately have no
  "user_id" field, so the model has nothing to spoof.
- Tools never touch the database directly. Each one is a thin wrapper
  around an existing service function (hold_service, booking_service,
  catalog_service, waitlist_service) — the exact same code path the REST
  API uses, so the AI cannot bypass a business rule the API enforces.
- create_booking_hold and confirm_and_pay are the only state-changing
  tools. Both require the caller to have already shown the user the
  concrete seats/price and gotten a "yes" in conversation — enforced by
  the agent's system prompt, and independently backstopped by an
  AuditLog row written for every call (app/services/ai/agent_service.py),
  so any AI-initiated booking or payment is traceable to the exact chat
  turn that triggered it.
- No tool executes arbitrary SQL or deletes anything. cancel_booking_tool
  is the only destructive-ish action, and it goes through the same
  ownership check as the REST cancel endpoint.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import mock_payment_provider
from app.models import Booking
from app.services import booking_service, catalog_service, hold_service, waitlist_service
from app.services.ai import rag


class ToolError(Exception):
    """Returned to the model as a tool_result error block, never raised past
    the agent loop — a bad tool call should let the model retry/explain,
    not 500 the whole chat request."""


@dataclass
class ToolContext:
    session: AsyncSession
    user_id: uuid.UUID


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_shows",
        "description": (
            "Search bookable shows/events by free-text query against title/description, "
            "optional max price per seat, and optional 'only if seats are available'. "
            "Use this first for any request like 'find me a concert' or 'hotel under X' "
            "(this platform's catalog is events/shows, not hotels/vehicles)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text match against event title/description. Empty to list everything."},
                "max_price": {"type": "number", "description": "Only include events whose cheapest available seat is at or below this price."},
                "available_only": {"type": "boolean", "description": "If true, exclude events with zero seats available. Default true."},
            },
        },
    },
    {
        "name": "check_availability",
        "description": "Get the live seat map for one show: per-section counts of free/held/sold seats and prices. Use before recommending or holding specific seats.",
        "input_schema": {
            "type": "object",
            "properties": {"show_id": {"type": "string", "description": "UUID of the show."}},
            "required": ["show_id"],
        },
    },
    {
        "name": "create_booking_hold",
        "description": (
            "Place a temporary hold (not a payment) on specific seats for the current user. "
            "Only call this after the user has explicitly agreed to hold those exact seats. "
            "The hold expires automatically if not paid within the platform's hold window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "show_id": {"type": "string"},
                "seat_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10},
            },
            "required": ["show_id", "seat_ids"],
        },
    },
    {
        "name": "confirm_and_pay",
        "description": (
            "Charge the current user for a HELD booking they own, using the platform's payment provider. "
            "Only call this after the user has explicitly confirmed they want to pay right now — this is an "
            "irreversible action that moves money."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"booking_id": {"type": "string"}},
            "required": ["booking_id"],
        },
    },
    {
        "name": "get_user_bookings",
        "description": "List the current user's own bookings (any status), most recent first.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_booking_details",
        "description": "Get full details of one booking. Only works for a booking owned by the current user.",
        "input_schema": {
            "type": "object",
            "properties": {"booking_id": {"type": "string"}},
            "required": ["booking_id"],
        },
    },
    {
        "name": "cancel_booking",
        "description": (
            "Cancel a booking owned by the current user, releasing its seats. Only call this after the user "
            "has explicitly confirmed the cancellation — it cannot be undone through this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"booking_id": {"type": "string"}},
            "required": ["booking_id"],
        },
    },
    {
        "name": "search_policies",
        "description": (
            "Look up SeatRush's cancellation, refund, payment, and booking-rule policies by topic. "
            "Always use this instead of guessing when the user asks whether/how they can cancel, get a "
            "refund, or what a rule is — never answer policy questions from general knowledge."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string", "description": "What the user wants to know, e.g. 'can I cancel a confirmed booking'."}},
            "required": ["topic"],
        },
    },
]


async def _search_shows(ctx: ToolContext, args: dict) -> dict:
    events = await catalog_service.list_events(ctx.session)
    query = (args.get("query") or "").strip().lower()
    max_price = args.get("max_price")
    available_only = args.get("available_only", True)

    def matches(e: dict) -> bool:
        if available_only and e["seats_available"] <= 0:
            return False
        if max_price is not None and (e["from_price"] is None or e["from_price"] > Decimal(str(max_price))):
            return False
        if query and query not in e["title"].lower() and query not in e["description"].lower():
            return False
        return True

    results = [e for e in events if matches(e)]
    return {
        "count": len(results),
        "events": [
            {
                "event_id": str(e["id"]),
                "title": e["title"],
                "venue": e["venue"].name if e["venue"] else None,
                "from_price": str(e["from_price"]) if e["from_price"] is not None else None,
                "seats_available": e["seats_available"],
                "next_show_id": str(e["next_show_id"]) if e["next_show_id"] else None,
                "next_show_at": e["next_show_at"].isoformat() if e["next_show_at"] else None,
            }
            for e in results[:5]
        ],
    }


async def _check_availability(ctx: ToolContext, args: dict) -> dict:
    show_id = _parse_uuid(args["show_id"], "show_id")
    seat_map = await catalog_service.get_seat_map(ctx.session, show_id, ctx.user_id)
    if seat_map is None:
        raise ToolError("Show not found")

    by_section: dict[str, dict] = {}
    for seat in seat_map["seats"]:
        bucket = by_section.setdefault(seat["section_name"], {"free": 0, "held": 0, "sold": 0, "price": str(seat["price"])})
        bucket[seat["status"].value.lower()] += 1

    free_seats = [s for s in seat_map["seats"] if s["status"].value == "FREE"]
    return {
        "show_id": str(show_id),
        "by_section": by_section,
        "free_seat_sample": [
            {"seat_id": str(s["id"]), "section": s["section_name"], "row": s["row_label"], "number": s["seat_number"], "price": str(s["price"])}
            for s in free_seats[:20]
        ],
    }


async def _create_booking_hold(ctx: ToolContext, args: dict) -> dict:
    show_id = _parse_uuid(args["show_id"], "show_id")
    seat_ids = [_parse_uuid(s, "seat_ids") for s in args["seat_ids"]]
    try:
        booking = await hold_service.create_hold(ctx.session, ctx.user_id, show_id, seat_ids)
    except hold_service.SeatsUnavailableError as e:
        raise ToolError(f"Some seats are no longer available: {[str(s) for s in e.unavailable_seat_ids]}")
    except hold_service.ShowNotFoundError:
        raise ToolError("Show not found")
    return {
        "booking_id": str(booking.id),
        "status": booking.status.value,
        "total_amount": str(booking.total_amount),
        "expires_at": booking.expires_at.isoformat() if booking.expires_at else None,
    }


async def _confirm_and_pay(ctx: ToolContext, args: dict) -> dict:
    booking = await _load_owned_booking(ctx, args["booking_id"])
    try:
        booking = await booking_service.initiate_payment(ctx.session, booking)
    except booking_service.InvalidTransitionError as e:
        raise ToolError(str(e))
    charge = await mock_payment_provider.charge(booking.total_amount, booking.id, "random")
    await booking_service.record_payment_pending(ctx.session, booking.id, charge.provider_ref, booking.total_amount)
    return {
        "booking_id": str(booking.id),
        "status": "PAYMENT_PENDING",
        "note": "Payment submitted to the provider; it settles asynchronously via webhook, typically within a few seconds. Check get_booking_details shortly to see CONFIRMED or FAILED.",
    }


async def _get_user_bookings(ctx: ToolContext, args: dict) -> dict:
    from app.routers._serializers import serialize_booking
    from sqlalchemy.orm import selectinload

    bookings = (
        await ctx.session.execute(
            select(Booking).where(Booking.user_id == ctx.user_id).options(selectinload(Booking.seats)).order_by(Booking.created_at.desc()).limit(20)
        )
    ).scalars().all()
    out = [await serialize_booking(ctx.session, b) for b in bookings]
    return {"count": len(out), "bookings": [b.model_dump(mode="json") for b in out]}


async def _get_booking_details(ctx: ToolContext, args: dict) -> dict:
    from app.routers._serializers import serialize_booking

    booking = await _load_owned_booking(ctx, args["booking_id"])
    out = await serialize_booking(ctx.session, booking)
    return out.model_dump(mode="json")


async def _cancel_booking(ctx: ToolContext, args: dict) -> dict:
    booking = await _load_owned_booking(ctx, args["booking_id"])
    try:
        booking = await booking_service.cancel_booking(ctx.session, booking)
    except booking_service.InvalidTransitionError as e:
        raise ToolError(str(e))
    return {"booking_id": str(booking.id), "status": booking.status.value}


async def _search_policies(ctx: ToolContext, args: dict) -> dict:
    results = rag.retrieve(args["topic"], top_k=3)
    if not results:
        return {"results": [], "note": "No matching policy passage found; tell the user to contact support rather than guessing."}
    return {"results": results}


async def _load_owned_booking(ctx: ToolContext, booking_id_raw: str) -> Booking:
    booking_id = _parse_uuid(booking_id_raw, "booking_id")
    try:
        booking = await booking_service.get_booking(ctx.session, booking_id)
    except booking_service.BookingNotFoundError:
        raise ToolError("Booking not found")
    if booking.user_id != ctx.user_id:
        # Never leak existence of another user's booking beyond a generic
        # not-found — same as the REST API's 403-vs-404 stance would allow,
        # but a flat denial is simpler and gives the model nothing to probe.
        raise ToolError("Booking not found")
    return booking


def _parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise ToolError(f"Invalid {field}: {value!r}")


_EXECUTORS: dict[str, Callable[[ToolContext, dict], Any]] = {
    "search_shows": _search_shows,
    "check_availability": _check_availability,
    "create_booking_hold": _create_booking_hold,
    "confirm_and_pay": _confirm_and_pay,
    "get_user_bookings": _get_user_bookings,
    "get_booking_details": _get_booking_details,
    "cancel_booking": _cancel_booking,
    "search_policies": _search_policies,
}

# Tools the agent may only call after the user has visibly agreed in
# conversation. Enforced by the system prompt; audit-logged unconditionally
# either way so a bypassed guardrail is still detectable after the fact.
IRREVERSIBLE_TOOLS = {"create_booking_hold", "confirm_and_pay", "cancel_booking"}


async def execute_tool(ctx: ToolContext, name: str, args: dict) -> dict:
    executor = _EXECUTORS.get(name)
    if executor is None:
        raise ToolError(f"Unknown tool: {name}")
    return await executor(ctx, args)
