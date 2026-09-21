from fastapi import APIRouter

from app.db import SessionLocal
from app.schemas import WebhookPayload
from app.services import booking_service

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("/webhook")
async def payment_webhook(body: WebhookPayload):
    async with SessionLocal() as session:
        outcome = await booking_service.handle_webhook(session, body.provider_ref, body.booking_id, body.status)
    return {"outcome": outcome}
