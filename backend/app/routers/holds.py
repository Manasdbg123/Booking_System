from fastapi import APIRouter, Depends, Header, HTTPException

from app.db import SessionLocal
from app.deps import enforce_rate_limit, get_current_user
from app.models import Show, User
from app.routers._serializers import serialize_booking
from app.schemas import BookingOut, HoldRequest
from app.services import hold_service, queue_service
from app.services.idempotency_service import (
    IdempotencyInProgress,
    IdempotencyKeyReused,
    IdempotentResult,
    run_idempotent,
)

router = APIRouter(prefix="/api/holds", tags=["holds"])


@router.post("", response_model=BookingOut, dependencies=[Depends(enforce_rate_limit)])
async def create_hold(
    body: HoldRequest,
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    admission_token: str | None = Header(default=None, alias="X-Admission-Token"),
):
    async with SessionLocal() as session:
        show = await session.get(Show, body.show_id)
        if show and show.is_hot:
            if not admission_token or not queue_service.verify_admission_token(admission_token, body.show_id, user.id):
                raise HTTPException(status_code=403, detail="Admission token required for this show's waiting room")

    if not idempotency_key:
        return await _do_hold(user.id, body)

    async def handler() -> IdempotentResult:
        booking_out = await _do_hold(user.id, body)
        return IdempotentResult(status_code=201, body=booking_out.model_dump(mode="json"))

    try:
        result = await run_idempotent(idempotency_key, "POST /api/holds", body.model_dump(mode="json") | {"user_id": str(user.id)}, handler)
    except IdempotencyKeyReused as e:
        raise HTTPException(status_code=422, detail=str(e))
    except IdempotencyInProgress:
        raise HTTPException(status_code=409, detail="Request with this idempotency key is still being processed")

    return BookingOut.model_validate(result.body)


async def _do_hold(user_id, body: HoldRequest) -> BookingOut:
    async with SessionLocal() as session:
        try:
            booking = await hold_service.create_hold(session, user_id, body.show_id, body.seat_ids)
        except hold_service.SeatsUnavailableError as e:
            raise HTTPException(status_code=409, detail={"message": "Some seats are unavailable", "seat_ids": [str(s) for s in e.unavailable_seat_ids]})
        except hold_service.ShowNotFoundError:
            raise HTTPException(status_code=404, detail="Show not found")
        await session.refresh(booking, attribute_names=["seats"])
        return await serialize_booking(session, booking)
