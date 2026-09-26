import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from app.models import BookingStatus, SeatStatus, WaitlistStatus


# ---- auth ----
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ---- catalog ----
class SectionOut(BaseModel):
    id: uuid.UUID
    name: str
    base_price: Decimal
    color: str

    class Config:
        from_attributes = True


class SeatOut(BaseModel):
    id: uuid.UUID
    row_label: str
    seat_number: int
    section_id: uuid.UUID
    pos_x: float
    pos_y: float

    class Config:
        from_attributes = True


class VenueOut(BaseModel):
    id: uuid.UUID
    name: str
    address: str

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    poster_url: str
    venue: VenueOut
    from_price: Decimal | None = None
    seats_available: int = 0
    seats_total: int = 0
    next_show_at: datetime | None = None
    next_show_id: uuid.UUID | None = None
    is_hot: bool = False

    class Config:
        from_attributes = True


class ShowOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    starts_at: datetime
    status: str
    is_hot: bool

    class Config:
        from_attributes = True


class ShowSeatOut(BaseModel):
    id: uuid.UUID
    seat_id: uuid.UUID
    row_label: str
    seat_number: int
    section_id: uuid.UUID
    section_name: str
    section_color: str
    price: Decimal
    status: SeatStatus
    pos_x: float
    pos_y: float
    is_mine: bool = False


class SeatMapOut(BaseModel):
    show_id: uuid.UUID
    sections: list[SectionOut]
    seats: list[ShowSeatOut]


# ---- holds / bookings ----
class HoldRequest(BaseModel):
    show_id: uuid.UUID
    seat_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


class BookingSeatOut(BaseModel):
    show_seat_id: uuid.UUID
    row_label: str
    seat_number: int
    section_name: str
    price: Decimal


class BookingOut(BaseModel):
    id: uuid.UUID
    show_id: uuid.UUID
    status: BookingStatus
    total_amount: Decimal
    expires_at: datetime | None
    ticket_code: str | None
    created_at: datetime
    seats: list[BookingSeatOut]


class PayRequest(BaseModel):
    booking_id: uuid.UUID
    simulate: str = "random"  # success|failure|timeout|duplicate|random


class WebhookPayload(BaseModel):
    provider_ref: str
    booking_id: uuid.UUID
    amount: Decimal
    status: str


class CancelRequest(BaseModel):
    booking_id: uuid.UUID


# ---- waitlist ----
class WaitlistJoinRequest(BaseModel):
    show_id: uuid.UUID
    section_id: uuid.UUID


class WaitlistOut(BaseModel):
    id: uuid.UUID
    show_id: uuid.UUID
    section_id: uuid.UUID
    position: int
    status: WaitlistStatus
    offer_expires_at: datetime | None


# ---- queue / waiting room ----
class QueueJoinRequest(BaseModel):
    show_id: uuid.UUID


class QueueStatusOut(BaseModel):
    ticket_id: uuid.UUID
    position: int
    status: str
    admission_token: str | None
    estimated_wait_seconds: int


# ---- ai assistant ----
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None


class ToolCallOut(BaseModel):
    name: str
    input: dict
    outcome: str
    result: dict = {}


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    reply: str
    tool_calls: list[ToolCallOut]


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime


# ---- admin ----
class AdminMetricsOut(BaseModel):
    active_holds: int
    sales_last_hour: int
    queue_depth: int
    conflict_rate_pct: float
    p95_latency_ms: float
