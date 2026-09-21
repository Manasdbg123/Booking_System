from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Seat, Section, ShowSeat
from app.schemas import BookingOut, BookingSeatOut


async def serialize_booking(session: AsyncSession, booking: Booking) -> BookingOut:
    rows = (
        await session.execute(
            select(ShowSeat, Seat, Section)
            .join(Seat, Seat.id == ShowSeat.seat_id)
            .join(Section, Section.id == Seat.section_id)
            .where(ShowSeat.id.in_([bs.show_seat_id for bs in booking.seats]))
        )
    ).all()
    seats = [
        BookingSeatOut(
            show_seat_id=show_seat.id,
            row_label=seat.row_label,
            seat_number=seat.seat_number,
            section_name=section.name,
            price=show_seat.price,
        )
        for show_seat, seat, section in rows
    ]
    return BookingOut(
        id=booking.id,
        show_id=booking.show_id,
        status=booking.status,
        total_amount=booking.total_amount,
        expires_at=booking.expires_at,
        ticket_code=booking.ticket_code,
        created_at=booking.created_at,
        seats=seats,
    )
