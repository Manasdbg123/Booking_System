import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, Seat, Section, Show, ShowSeat


async def list_events(session: AsyncSession) -> list[Event]:
    result = await session.execute(select(Event).options(selectinload(Event.venue)))
    return list(result.scalars().all())


async def get_event(session: AsyncSession, event_id: uuid.UUID) -> Event | None:
    result = await session.execute(
        select(Event).where(Event.id == event_id).options(selectinload(Event.venue), selectinload(Event.shows))
    )
    return result.scalar_one_or_none()


async def get_show(session: AsyncSession, show_id: uuid.UUID) -> Show | None:
    return await session.get(Show, show_id)


async def get_seat_map(session: AsyncSession, show_id: uuid.UUID, viewer_user_id: uuid.UUID | None):
    show = await session.get(Show, show_id)
    if show is None:
        return None

    sections = (await session.execute(select(Section).where(Section.hall_id == show.hall_id))).scalars().all()

    rows = (
        await session.execute(
            select(ShowSeat, Seat)
            .join(Seat, Seat.id == ShowSeat.seat_id)
            .where(ShowSeat.show_id == show_id)
        )
    ).all()

    from app.models import Booking  # local import to avoid cycle at module load

    seats_out = []
    for show_seat, seat in rows:
        is_mine = False
        if viewer_user_id and show_seat.held_by_booking_id:
            booking = await session.get(Booking, show_seat.held_by_booking_id)
            is_mine = bool(booking and booking.user_id == viewer_user_id)
        section = next((s for s in sections if s.id == seat.section_id), None)
        seats_out.append(
            {
                "id": show_seat.id,
                "seat_id": seat.id,
                "row_label": seat.row_label,
                "seat_number": seat.seat_number,
                "section_id": seat.section_id,
                "section_name": section.name if section else "",
                "section_color": section.color if section else "#888",
                "price": show_seat.price,
                "status": show_seat.status,
                "pos_x": float(seat.pos_x),
                "pos_y": float(seat.pos_y),
                "is_mine": is_mine,
            }
        )

    return {"show_id": show_id, "sections": sections, "seats": seats_out}
