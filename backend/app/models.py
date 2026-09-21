import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class ShowStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class SeatStatus(str, enum.Enum):
    FREE = "FREE"
    HELD = "HELD"
    SOLD = "SOLD"


class BookingStatus(str, enum.Enum):
    HELD = "HELD"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    REFUNDED = "REFUNDED"


class WaitlistStatus(str, enum.Enum):
    WAITING = "WAITING"
    OFFERED = "OFFERED"
    EXPIRED = "EXPIRED"
    CLAIMED = "CLAIMED"
    CANCELLED = "CANCELLED"


class QueueStatus(str, enum.Enum):
    WAITING = "WAITING"
    ADMITTED = "ADMITTED"
    EXPIRED = "EXPIRED"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.USER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(500), default="")

    halls: Mapped[list["Hall"]] = relationship(back_populates="venue")


class Hall(Base):
    __tablename__ = "halls"
    id: Mapped[uuid.UUID] = uuid_pk()
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    name: Mapped[str] = mapped_column(String(255))

    venue: Mapped[Venue] = relationship(back_populates="halls")
    sections: Mapped[list["Section"]] = relationship(back_populates="hall")
    seats: Mapped[list["Seat"]] = relationship(back_populates="hall")


class Section(Base):
    __tablename__ = "sections"
    id: Mapped[uuid.UUID] = uuid_pk()
    hall_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("halls.id"))
    name: Mapped[str] = mapped_column(String(100))
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    color: Mapped[str] = mapped_column(String(20), default="#6366f1")

    hall: Mapped[Hall] = relationship(back_populates="sections")
    seats: Mapped[list["Seat"]] = relationship(back_populates="section")


class Seat(Base):
    __tablename__ = "seats"
    id: Mapped[uuid.UUID] = uuid_pk()
    hall_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("halls.id"))
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sections.id"))
    row_label: Mapped[str] = mapped_column(String(10))
    seat_number: Mapped[int] = mapped_column(Integer)
    pos_x: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    pos_y: Mapped[float] = mapped_column(Numeric(8, 2), default=0)

    hall: Mapped[Hall] = relationship(back_populates="seats")
    section: Mapped[Section] = relationship(back_populates="seats")

    __table_args__ = (UniqueConstraint("hall_id", "row_label", "seat_number", name="uq_seat_position"),)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000), default="")
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    poster_url: Mapped[str] = mapped_column(String(500), default="")

    venue: Mapped[Venue] = relationship()
    shows: Mapped[list["Show"]] = relationship(back_populates="event")


class Show(Base):
    __tablename__ = "shows"
    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    hall_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("halls.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[ShowStatus] = mapped_column(Enum(ShowStatus, name="show_status"), default=ShowStatus.SCHEDULED)
    is_hot: Mapped[bool] = mapped_column(default=False)  # triggers waiting room

    event: Mapped[Event] = relationship(back_populates="shows")
    hall: Mapped[Hall] = relationship()
    show_seats: Mapped[list["ShowSeat"]] = relationship(back_populates="show")


class ShowSeat(Base):
    """The hot table: one row per seat per show. status is the lock."""

    __tablename__ = "show_seats"
    id: Mapped[uuid.UUID] = uuid_pk()
    show_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shows.id"))
    seat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seats.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[SeatStatus] = mapped_column(Enum(SeatStatus, name="seat_status"), default=SeatStatus.FREE)
    # Named explicitly: use_alter FKs are emitted as separate ADD/DROP
    # CONSTRAINT statements, which require a stable name. (show_seats and
    # bookings reference each other, hence use_alter.)
    held_by_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bookings.id", use_alter=True, name="fk_show_seats_held_by_booking"), nullable=True
    )
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0)  # optimistic-lock counter, bumped every transition

    show: Mapped[Show] = relationship(back_populates="show_seats")
    seat: Mapped[Seat] = relationship()

    __table_args__ = (
        UniqueConstraint("show_id", "seat_id", name="uq_show_seat"),
        Index("ix_show_seats_show_status", "show_id", "status"),
    )


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    show_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shows.id"))
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus, name="booking_status"), default=BookingStatus.HELD)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    ticket_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    seats: Mapped[list["BookingSeat"]] = relationship(back_populates="booking")


class BookingSeat(Base):
    __tablename__ = "booking_seats"
    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    show_seat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("show_seats.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    booking: Mapped[Booking] = relationship(back_populates="seats")

    __table_args__ = (UniqueConstraint("booking_id", "show_seat_id", name="uq_booking_seat"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_progress: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[uuid.UUID] = uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    provider_ref: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    raw_webhook_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    id: Mapped[uuid.UUID] = uuid_pk()
    show_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shows.id"))
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sections.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[WaitlistStatus] = mapped_column(Enum(WaitlistStatus, name="waitlist_status"), default=WaitlistStatus.WAITING)
    offered_show_seat_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("show_seats.id"), nullable=True)
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_waitlist_show_section_status_position", "show_id", "section_id", "status", "position"),
    )


class QueueTicket(Base):
    __tablename__ = "queue_tickets"
    id: Mapped[uuid.UUID] = uuid_pk()
    show_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shows.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    token: Mapped[str] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[QueueStatus] = mapped_column(Enum(QueueStatus, name="queue_status"), default=QueueStatus.WAITING)
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    aggregate_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_outbox_unpublished", "published_at"),)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = uuid_pk()
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(255))
    entity: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    reasoning: Mapped[str] = mapped_column(String(2000), default="")
    outcome: Mapped[str] = mapped_column(String(100), default="")
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
