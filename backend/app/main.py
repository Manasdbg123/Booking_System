import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger, new_request_id
from app.core.security import hash_password
from app.config import settings
from app.db import SessionLocal
from app.models import User, UserRole
from app.routers import admin, ai, auth, bookings, catalog, health, holds, payments, queue, realtime, waitlist

configure_logging()
logger = get_logger("seatrush")

app = FastAPI(title="SeatRush API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = new_request_id()
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = rid
    logger.info("request", method=request.method, path=request.url.path, status=response.status_code, duration_ms=round(duration_ms, 2))
    return response


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


for router in (auth.router, catalog.router, holds.router, bookings.router, payments.router, waitlist.router, queue.router, admin.router, ai.router, realtime.router, health.router):
    app.include_router(router)


@app.on_event("startup")
async def startup():
    logger.info("startup", environment="seatrush-api")
    async with SessionLocal() as session:
        existing = (await session.execute(select(User).where(User.email == settings.admin_bootstrap_email))).scalar_one_or_none()
        if existing is None:
            session.add(
                User(
                    email=settings.admin_bootstrap_email,
                    password_hash=hash_password(settings.admin_bootstrap_password),
                    role=UserRole.ADMIN,
                )
            )
            await session.commit()
            logger.info("admin_bootstrapped", email=settings.admin_bootstrap_email)
