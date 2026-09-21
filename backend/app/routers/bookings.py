import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, get_session
from app.deps import get_current_user
from app.models import Booking, User
from app.routers._serializers import serialize_booking
from app.schemas import BookingOut, CancelRequest, PayRequest
from app import mock_payment_provider
from app.services import booking_service
from app.services.idempotency_service import (
    IdempotencyInProgress,
    IdempotencyKeyReused,
    IdempotentResult,
    run_idempotent,
)

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.get("", response_model=list[BookingOut])
async def my_bookings(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    bookings = (
        await session.execute(
            select(Booking).where(Booking.user_id == user.id).options(selectinload(Booking.seats)).order_by(Booking.created_at.desc())
        )
    ).scalars().all()
    return [await serialize_booking(session, b) for b in bookings]


@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(booking_id: uuid.UUID, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    try:
        booking = await booking_service.get_booking(session, booking_id)
    except booking_service.BookingNotFoundError:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    return await serialize_booking(session, booking)


@router.post("/pay", response_model=BookingOut)
async def pay(
    body: PayRequest,
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    async def do_pay() -> BookingOut:
        async with SessionLocal() as session:
            try:
                booking = await booking_service.get_booking(session, body.booking_id)
            except booking_service.BookingNotFoundError:
                raise HTTPException(status_code=404, detail="Booking not found")
            if booking.user_id != user.id:
                raise HTTPException(status_code=403, detail="Not your booking")
            try:
                booking = await booking_service.initiate_payment(session, booking)
            except booking_service.InvalidTransitionError as e:
                raise HTTPException(status_code=409, detail=str(e))

            charge = await mock_payment_provider.charge(booking.total_amount, booking.id, body.simulate)
            await booking_service.record_payment_pending(session, booking.id, charge.provider_ref, booking.total_amount)
            await session.refresh(booking, attribute_names=["seats"])
            return await serialize_booking(session, booking)

    if not idempotency_key:
        return await do_pay()

    async def handler() -> IdempotentResult:
        out = await do_pay()
        return IdempotentResult(status_code=200, body=out.model_dump(mode="json"))

    try:
        result = await run_idempotent(idempotency_key, "POST /api/bookings/pay", body.model_dump(mode="json") | {"user_id": str(user.id)}, handler)
    except IdempotencyKeyReused as e:
        raise HTTPException(status_code=422, detail=str(e))
    except IdempotencyInProgress:
        raise HTTPException(status_code=409, detail="Request with this idempotency key is still being processed")
    return BookingOut.model_validate(result.body)


@router.post("/cancel", response_model=BookingOut)
async def cancel(body: CancelRequest, user: User = Depends(get_current_user)):
    async with SessionLocal() as session:
        try:
            booking = await booking_service.get_booking(session, body.booking_id)
        except booking_service.BookingNotFoundError:
            raise HTTPException(status_code=404, detail="Booking not found")
        if booking.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not your booking")
        try:
            booking = await booking_service.cancel_booking(session, booking)
        except booking_service.InvalidTransitionError as e:
            raise HTTPException(status_code=409, detail=str(e))
        await session.refresh(booking, attribute_names=["seats"])
        return await serialize_booking(session, booking)
