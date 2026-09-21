"""Seeds a realistic dataset: several venues, 5-10 events, shows with
500-5000 seats each. Run with: python -m scripts.seed (from backend/).
Idempotent-ish: clears existing catalog/booking data first (dev only).
"""

import asyncio
import math
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


# Hall geometry. Seats are laid out in aisle-separated blocks, curved around
# the stage, with sections as contiguous front-to-back bands (the expensive
# seats are the ones near the stage) rather than being sprinkled seat by seat.
SEAT_PITCH = 14.0
ROW_PITCH = 16.0
AISLE_WIDTH = 22.0

# Front-to-back share of rows per section, matching SECTION_TEMPLATES order.
SECTION_ROW_SHARE = (0.15, 0.25, 0.28, 0.32)


def hall_shape(n: int) -> tuple[int, tuple[int, int, int]]:
    """Seats per row and the (left, centre, right) block split for a hall of n seats.

    A fixed seats-per-row makes big halls absurd: 5,000 seats at 40 per row
    is 125 rows, which renders as a tall narrow tower rather than a venue.
    Deriving the row width from the seat count keeps every hall roughly
    1.3–1.7x wider than deep, like a real auditorium.
    """
    seats_per_row = max(20, min(100, round(math.sqrt(n * 1.7))))
    seats_per_row -= seats_per_row % 2  # keep the side blocks symmetric
    side = max(4, seats_per_row // 4)
    centre = seats_per_row - 2 * side
    return seats_per_row, (side, centre, side)


def _x_for_seat_in_row(index_in_row: int, blocks: tuple[int, int, int]) -> float:
    """X position accounting for the aisles between seat blocks."""
    remaining = index_in_row
    for block_i, block_size in enumerate(blocks):
        if remaining < block_size:
            seats_before = sum(blocks[:block_i]) + remaining
            return seats_before * SEAT_PITCH + block_i * AISLE_WIDTH
        remaining -= block_size
    # more seats in the row than the blocks allow for — put them on the end
    return (sum(blocks) + remaining) * SEAT_PITCH + len(blocks) * AISLE_WIDTH


def _section_index_for_row(row: int, total_rows: int) -> int:
    """Sections are contiguous bands of rows, closest-to-stage first."""
    boundary = 0.0
    for section_i, share in enumerate(SECTION_ROW_SHARE):
        boundary += share * total_rows
        if row < boundary:
            return section_i
    return len(SECTION_ROW_SHARE) - 1


def make_seats(n: int) -> list[tuple[str, int, int, float, float]]:
    """Returns (row_label, seat_number, section_index, pos_x, pos_y) per seat."""
    seats_per_row, blocks = hall_shape(n)
    total_rows = (n + seats_per_row - 1) // seats_per_row
    row_width = sum(blocks) * SEAT_PITCH + (len(blocks) - 1) * AISLE_WIDTH
    centre_x = row_width / 2
    # Keep the arc proportional to the hall's width so wide halls don't get
    # an exaggerated bow at the edges.
    curve = 32.0 / max(centre_x * centre_x, 1.0)

    seats = []
    for i in range(n):
        row = i // seats_per_row
        index_in_row = i % seats_per_row
        x = _x_for_seat_in_row(index_in_row, blocks)
        offset_from_centre = x - centre_x
        y = row * ROW_PITCH + curve * offset_from_centre * offset_from_centre
        seats.append((row_label(row), index_in_row + 1, _section_index_for_row(row, total_rows), x, y))
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
            for row, seat_number, section_index, pos_x, pos_y in make_seats(seat_count):
                section = sections[section_index]
                seat = Seat(
                    hall_id=hall.id, section_id=section.id, row_label=row, seat_number=seat_number,
                    pos_x=pos_x, pos_y=pos_y,
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

            spr, _ = hall_shape(seat_count)
            print(f"  - {title}: {seat_count} seats, {spr}/row x {(seat_count + spr - 1)//spr} rows, {len(sections)} sections")

        await session.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
