"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("USER", "ADMIN", name="user_role"), nullable=False, server_default="USER"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "venues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), nullable=False, server_default=""),
    )

    op.create_table(
        "halls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("venues.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
    )

    op.create_table(
        "sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("hall_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("halls.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("color", sa.String(20), nullable=False, server_default="#6366f1"),
    )

    op.create_table(
        "seats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("hall_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("halls.id"), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("row_label", sa.String(10), nullable=False),
        sa.Column("seat_number", sa.Integer, nullable=False),
        sa.Column("pos_x", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("pos_y", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("hall_id", "row_label", "seat_number", name="uq_seat_position"),
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False, server_default=""),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("venues.id"), nullable=False),
        sa.Column("poster_url", sa.String(500), nullable=False, server_default=""),
    )

    op.create_table(
        "shows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("hall_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("halls.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Enum("SCHEDULED", "CANCELLED", "COMPLETED", name="show_status"), nullable=False, server_default="SCHEDULED"),
        sa.Column("is_hot", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("show_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shows.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("HELD", "PAYMENT_PENDING", "CONFIRMED", "FAILED", "EXPIRED", "CANCELLED", name="booking_status"),
            nullable=False,
            server_default="HELD",
        ),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("ticket_code", sa.String(32), nullable=True, unique=True),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bookings_idempotency_key", "bookings", ["idempotency_key"])
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_show_id", "bookings", ["show_id"])
    op.create_index("ix_bookings_expires_at", "bookings", ["expires_at"])

    op.create_table(
        "show_seats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("show_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shows.id"), nullable=False),
        sa.Column("seat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("seats.id"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.Enum("FREE", "HELD", "SOLD", name="seat_status"), nullable=False, server_default="FREE"),
        sa.Column(
            "held_by_booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", use_alter=True, name="fk_show_seats_held_by_booking"),
            nullable=True,
        ),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("show_id", "seat_id", name="uq_show_seat"),
    )
    op.create_index("ix_show_seats_show_status", "show_seats", ["show_id", "status"])

    op.create_table(
        "booking_seats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("show_seat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("show_seats.id"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.UniqueConstraint("booking_id", "show_seat_id", name="uq_booking_seat"),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("endpoint", sa.String(255), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_body", postgresql.JSONB, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("in_progress", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("provider_ref", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SUCCEEDED", "FAILED", "TIMEOUT", "REFUNDED", name="payment_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("raw_webhook_payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "waitlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("show_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shows.id"), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column(
            "status",
            sa.Enum("WAITING", "OFFERED", "EXPIRED", "CLAIMED", "CANCELLED", name="waitlist_status"),
            nullable=False,
            server_default="WAITING",
        ),
        sa.Column("offered_show_seat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("show_seats.id"), nullable=True),
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_waitlist_show_section_status_position", "waitlist_entries", ["show_id", "section_id", "status", "position"]
    )

    op.create_table(
        "queue_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("show_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shows.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(500), nullable=False, server_default=""),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("status", sa.Enum("WAITING", "ADMITTED", "EXPIRED", name="queue_status"), nullable=False, server_default="WAITING"),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_queue_tickets_show_status_position", "queue_tickets", ["show_id", "status", "position"])

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_unpublished", "outbox_events", ["published_at"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("entity", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("reasoning", sa.String(2000), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(100), nullable=False, server_default=""),
        sa.Column("extra", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("outbox_events")
    op.drop_table("queue_tickets")
    op.drop_table("waitlist_entries")
    op.drop_table("payments")
    op.drop_table("idempotency_keys")
    op.drop_table("booking_seats")
    op.drop_table("show_seats")
    op.drop_table("bookings")
    op.drop_table("shows")
    op.drop_table("events")
    op.drop_table("seats")
    op.drop_table("sections")
    op.drop_table("halls")
    op.drop_table("venues")
    op.drop_table("users")
    for enum_name in ("user_role", "show_status", "booking_status", "seat_status", "payment_status", "waitlist_status", "queue_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
