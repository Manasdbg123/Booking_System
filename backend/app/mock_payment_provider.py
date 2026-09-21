"""A mock payment provider that simulates a real gateway's async behavior:
you call charge(), get back a provider_ref immediately (PENDING), and the
"real" result arrives later via a webhook POST to /payments/webhook.

Controlled via the `simulate` field on the charge request so tests/demo UI
can force success / failure / timeout / duplicate-webhook scenarios.
"""

import asyncio
import random
import uuid
from dataclasses import dataclass
from decimal import Decimal

import httpx



@dataclass
class ChargeResult:
    provider_ref: str


async def charge(amount: Decimal, booking_id: uuid.UUID, simulate: str = "random") -> ChargeResult:
    provider_ref = f"mock_{uuid.uuid4().hex}"
    asyncio.create_task(_fire_webhook_later(provider_ref, booking_id, amount, simulate))
    return ChargeResult(provider_ref=provider_ref)


async def _fire_webhook_later(provider_ref: str, booking_id: uuid.UUID, amount: Decimal, simulate: str) -> None:
    delay = random.uniform(0.5, 2.5)
    await asyncio.sleep(delay)

    outcome = simulate
    if simulate == "random":
        outcome = random.choices(
            ["success", "failure", "timeout", "duplicate"],
            weights=[75, 10, 10, 5],
        )[0]

    if outcome == "timeout":
        return  # never call back — booking must eventually be reconciled/expired

    status = "SUCCEEDED" if outcome in ("success", "duplicate") else "FAILED"
    payload = {
        "provider_ref": provider_ref,
        "booking_id": str(booking_id),
        "amount": str(amount),
        "status": status,
    }

    async with httpx.AsyncClient() as client:
        try:
            await client.post("http://localhost:8000/api/payments/webhook", json=payload, timeout=5)
            if outcome == "duplicate":
                await asyncio.sleep(0.3)
                await client.post("http://localhost:8000/api/payments/webhook", json=payload, timeout=5)
        except httpx.HTTPError:
            pass
