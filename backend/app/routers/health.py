from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.db import get_session

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(get_session)):
    checks = {"database": False, "redis": False}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass
    try:
        await get_redis().ping()
        checks["redis"] = True
    except Exception:
        pass
    ready = all(checks.values())
    return {"ready": ready, "checks": checks}
