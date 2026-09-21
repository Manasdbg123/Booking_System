"""Test fixtures.

Requires a real Postgres reachable via TEST_DATABASE_URL (defaults to a
`seatrush_test` DB on localhost) and a real Redis via TEST_REDIS_URL. These
are NOT mocked, deliberately: the whole point of this test suite is proving
the concurrency guarantees hold against the real database engine's locking
behavior, which an in-memory/SQLite substitute would not faithfully
reproduce (see PLAN.md's locking-strategy rationale).
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://seatrush:seatrush@localhost:5432/seatrush_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

from app.config import settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.models import Event, Hall, Section, Seat, Show, ShowSeat, User, UserRole, Venue  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.redis_client import get_redis  # noqa: E402

test_engine = create_async_engine(settings.database_url)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_schema():
    # Guard: this fixture wipes the entire schema, so refuse to run unless the
    # target database is clearly a throwaway test database.
    db_name = settings.database_url.rsplit("/", 1)[-1]
    assert db_name.endswith("_test"), f"Refusing to wipe non-test database {db_name!r}"

    # DROP SCHEMA rather than metadata.drop_all: it also clears leftovers from
    # older schema versions (renamed constraints, dropped tables) that drop_all
    # can't see, so a stale test DB can never fail the run.
    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await test_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    redis = get_redis()
    await redis.flushdb()
    yield


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_show(db_session):
    """One venue/hall/section/50 seats/one show — enough contention surface
    for concurrency tests without the cost of thousands of rows."""
    venue = Venue(name="Test Venue", address="Nowhere")
    db_session.add(venue)
    await db_session.flush()
    hall = Hall(venue_id=venue.id, name="Main Hall")
    db_session.add(hall)
    await db_session.flush()
    section = Section(hall_id=hall.id, name="General", base_price=Decimal("500"))
    db_session.add(section)
    await db_session.flush()
    event = Event(title="Test Event", venue_id=venue.id)
    db_session.add(event)
    await db_session.flush()
    show = Show(event_id=event.id, hall_id=hall.id, starts_at=datetime(2027, 1, 1, 18, 0, tzinfo=timezone.utc))
    db_session.add(show)
    await db_session.flush()

    seats = []
    show_seats = []
    for i in range(50):
        seat = Seat(hall_id=hall.id, section_id=section.id, row_label="A", seat_number=i + 1)
        db_session.add(seat)
        seats.append(seat)
    await db_session.flush()
    for seat in seats:
        ss = ShowSeat(show_id=show.id, seat_id=seat.id, price=section.base_price)
        db_session.add(ss)
        show_seats.append(ss)
    await db_session.commit()

    return {"show": show, "section": section, "seats": seats, "show_seats": show_seats}


@pytest_asyncio.fixture
async def user(db_session):
    u = User(email=f"user-{uuid.uuid4().hex[:8]}@test.dev", password_hash=hash_password("password123"), role=UserRole.USER)
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


# Hashed once per session, not once per user: bcrypt is ~250ms a call, and the
# concurrency tests need hundreds of users. What they're testing is seat
# contention, not password hashing, so every test user shares this hash.
STATIC_PASSWORD_HASH = hash_password("password123")


async def create_users(n: int) -> list[uuid.UUID]:
    """Bulk-creates n users in a single transaction and returns their ids."""
    from app.db import SessionLocal

    async with SessionLocal() as session:
        users = [
            User(email=f"u-{uuid.uuid4().hex[:12]}@test.dev", password_hash=STATIC_PASSWORD_HASH, role=UserRole.USER)
            for _ in range(n)
        ]
        session.add_all(users)
        await session.commit()
        return [u.id for u in users]
