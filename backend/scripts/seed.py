"""Seeds a realistic dataset: several venues, 5-10 events, shows with
500-5000 seats each. Run with: python -m scripts.seed (from backend/).
Idempotent-ish: clears existing catalog/booking data first (dev only).
"""

import asyncio
import random
import string
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.db import SessionLocal
from app.models import Event, Hall, Section, Seat, Show, ShowSeat, Venue

SECTION_TEMPLATES = [
    ("Platinum", Decimal("2500"), "#f59e0b"),
    ("Gold", Decimal("1500"), "#eab308"),
    ("Silver", Decimal("900"), "#94a3b8"),
    ("General", Decimal("400"), "#6366f1"),
]

VENUES = [
    ("Grand Arena", "MG Road, Bengaluru"),
    ("Skyline Convention Center", "Bandra Kurla Complex, Mumbai"),
    ("Riverside Stadium", "Sector 29, Gurugram"),
    ("The Metropolitan Hall", "Connaught Place, Delhi"),
]

EVENTS = [
    ("Arijit Singh — Live in Concert", "An unforgettable evening of soulful music.", 4000),
    ("Coldplay: Music of the Spheres", "The world tour comes to India.", 5000),
    ("Stand-Up Comedy Night", "An evening of laughter with top comedians.", 800),
    ("Kabir Singh Live Theatre", "A gripping stage adaptation.", 600),
    ("Tech Conclave 2026", "Keynotes and panels from industry leaders.", 1200),
    ("Sunburn Festival Warmup", "EDM night featuring top DJs.", 3000),
    ("Classical Symphony Evening", "An orchestral performance for the ages.", 500),
]


def row_label(index: int) -> str:
    """Spreadsheet-style labels so large halls don't run out: A..Z, AA..AZ, BA.."""
    label = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        label = string.ascii_uppercase[remainder] + label
    return label


def make_seats(n: int) -> list[tuple[str, int]]:
    seats_per_row = 40
    seats = []
    for i in range(n):
        seats.append((row_label(i // seats_per_row), i % seats_per_row + 1))
    return seats


async def seed() -> None:
    async with SessionLocal() as session:
        print("Clearing existing catalog data...")
        for table in (
            "outbox_events", "audit_log", "booking_seats", "payments", "bookings",
            "waitlist_entries", "queue_tickets", "show_seats", "shows", "events",
            "seats", "sections", "halls", "venues",
        ):
            await session.execute(text(f"DELETE FROM {table}"))
        await session.commit()

        venues = []
        for name, address in VENUES:
            v = Venue(name=name, address=address)
            session.add(v)
            venues.append(v)
        await session.flush()

        print("Creating events and shows with seat maps...")
        for i, (title, desc, seat_count) in enumerate(EVENTS):
            venue = venues[i % len(venues)]
            # One hall per event: seats and sections are hall-scoped, so sharing
            # a hall across events would collide on uq_seat_position.
            hall = Hall(venue_id=venue.id, name=f"{venue.name} — Hall {i + 1}")
            session.add(hall)
            await session.flush()

            event = Event(title=title, description=desc, venue_id=venue.id, poster_url=f"/posters/event-{i+1}.jpg")
            session.add(event)
            await session.flush()

            sections = []
            for name, price, color in SECTION_TEMPLATES:
                sec = Section(hall_id=hall.id, name=name, base_price=price, color=color)
                session.add(sec)
                sections.append(sec)
            await session.flush()

            seats_by_section: dict = {sec.id: [] for sec in sections}
            for idx, (row, seat_number) in enumerate(make_seats(seat_count)):
                section = sections[idx % len(sections)]
                seat = Seat(
                    hall_id=hall.id, section_id=section.id, row_label=row, seat_number=seat_number,
                    pos_x=seat_number * 12, pos_y=(idx // 40) * 14,
                )
                session.add(seat)
                seats_by_section[section.id].append(seat)
            await session.flush()

            show = Show(
                event_id=event.id, hall_id=hall.id,
                starts_at=datetime.now(timezone.utc) + timedelta(days=7 + i * 3, hours=random.randint(0, 12)),
                is_hot=(i == 0),  # first event's show demonstrates the waiting room
            )
            session.add(show)
            await session.flush()

            for section in sections:
                for seat in seats_by_section[section.id]:
                    session.add(ShowSeat(show_id=show.id, seat_id=seat.id, price=section.base_price))

            print(f"  - {title}: {seat_count} seats across {len(sections)} sections")

        await session.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
