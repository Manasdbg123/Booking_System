"""Generic idempotency-key handling for mutating endpoints.

Strategy: the idempotency_keys table has a composite primary key
(key, endpoint), so INSERT ... ON CONFLICT DO NOTHING is atomic across
concurrent requests carrying the same key. Whichever request's INSERT
actually lands "wins" and runs the handler; every other concurrent request
with the same key sees the conflict and polls briefly for the winner's
result (it's mid-flight for at most the handler's runtime, which for a
seat hold is milliseconds). A request that reuses a key with a different
payload gets a 422 rather than silently returning the wrong cached result.
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal


class IdempotencyKeyReused(Exception):
    """Same key used with a materially different request body."""


class IdempotencyInProgress(Exception):
    """Another request with the same key is still being processed."""


@dataclass
class IdempotentResult:
    status_code: int
    body: dict


def hash_request(payload: dict) -> str:
    normalized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


async def run_idempotent(
    key: str,
    endpoint: str,
    request_payload: dict,
    handler: Callable[[], Awaitable[IdempotentResult]],
) -> IdempotentResult:
    request_hash = hash_request(request_payload)

    async with SessionLocal() as claim_session:
        claimed = await _try_claim(claim_session, key, endpoint, request_hash)

    if not claimed:
        return await _wait_for_result(key, endpoint, request_hash)

    try:
        result = await handler()
    except Exception:
        async with SessionLocal() as session:
            await session.execute(
                text(
                    "DELETE FROM idempotency_keys WHERE key = :key AND endpoint = :endpoint AND in_progress = true"
                ),
                {"key": key, "endpoint": endpoint},
            )
            await session.commit()
        raise

    async with SessionLocal() as session:
        await session.execute(
            text(
                """
                UPDATE idempotency_keys
                SET response_body = CAST(:body AS JSONB), status_code = :status_code, in_progress = false
                WHERE key = :key AND endpoint = :endpoint
                """
            ),
            {
                "body": json.dumps(result.body, default=str),
                "status_code": result.status_code,
                "key": key,
                "endpoint": endpoint,
            },
        )
        await session.commit()

    return result


async def _try_claim(session: AsyncSession, key: str, endpoint: str, request_hash: str) -> bool:
    res = await session.execute(
        text(
            """
            INSERT INTO idempotency_keys (key, endpoint, request_hash, in_progress)
            VALUES (:key, :endpoint, :request_hash, true)
            ON CONFLICT (key, endpoint) DO NOTHING
            RETURNING key
            """
        ),
        {"key": key, "endpoint": endpoint, "request_hash": request_hash},
    )
    await session.commit()
    return res.first() is not None


async def _wait_for_result(key: str, endpoint: str, request_hash: str, timeout: float = 10.0) -> IdempotentResult:
    waited = 0.0
    interval = 0.1
    while waited < timeout:
        async with SessionLocal() as session:
            row = await session.execute(
                text(
                    "SELECT request_hash, response_body, status_code, in_progress FROM idempotency_keys "
                    "WHERE key = :key AND endpoint = :endpoint"
                ),
                {"key": key, "endpoint": endpoint},
            )
            record = row.first()

        if record is None:
            # the original claimant's row vanished (its handler raised) — retry claiming
            async with SessionLocal() as session:
                claimed = await _try_claim(session, key, endpoint, request_hash)
            if claimed:
                raise IdempotencyInProgress("retry")  # caller should re-invoke run_idempotent's handler path
            waited += interval
            await asyncio.sleep(interval)
            continue

        if record.request_hash != request_hash:
            raise IdempotencyKeyReused(f"Idempotency key {key} was already used with a different request body")

        if not record.in_progress:
            return IdempotentResult(status_code=record.status_code, body=record.response_body or {})

        await asyncio.sleep(interval)
        waited += interval

    raise IdempotencyInProgress("Timed out waiting for original request to complete")
