import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models import User, UserRole


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


async def register(session: AsyncSession, email: str, password: str) -> tuple[User, str]:
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise EmailAlreadyRegisteredError()
    # bcrypt is deliberately slow (~100-250ms). Running it inline would block
    # the event loop for that whole time, stalling every other in-flight
    # request and holding this request's pooled DB connection while it burns
    # CPU, so it goes to a worker thread.
    password_hash = await asyncio.to_thread(hash_password, password)
    user = User(email=email, password_hash=password_hash, role=UserRole.USER)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token = create_access_token(user.id, user.role.value)
    return user, token


async def login(session: AsyncSession, email: str, password: str) -> tuple[User, str]:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or not await asyncio.to_thread(verify_password, password, user.password_hash):
        raise InvalidCredentialsError()
    token = create_access_token(user.id, user.role.value)
    return user, token
