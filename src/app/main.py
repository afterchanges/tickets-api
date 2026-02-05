from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_client import Counter, Histogram, make_asgi_app
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from app.api.errors import install_exception_handlers
from app.api.routers.auth import router as auth_router
from app.api.routers.tickets import router as tickets_router
from app.core.logging import configure_logging, get_logger
from app.core.redis import redis_client
from app.core.settings import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.db.session import SessionLocal
from app.middlewares.request_id import RequestIdMiddleware
from app.models.enums import UserRole
from app.models.user import User


configure_logging(log_level=settings.log_level)
logger = get_logger(__name__)


REQUEST_COUNT = Counter(
	"http_requests_total",
	"Total HTTP requests",
	["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
	"http_request_duration_seconds",
	"HTTP request duration (seconds)",
	["method", "path"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next):
		start = time.perf_counter()
		status_code = 500
		response: Response
		try:
			response = await call_next(request)
			status_code = int(response.status_code)
			return response
		finally:
			duration = time.perf_counter() - start

			route = request.scope.get("route")
			path = getattr(route, "path", None) or request.url.path

			REQUEST_COUNT.labels(request.method, path, str(status_code)).inc()
			REQUEST_LATENCY.labels(request.method, path).observe(duration)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next):
		response = await call_next(request)
		response.headers.setdefault("X-Content-Type-Options", "nosniff")
		response.headers.setdefault("X-Frame-Options", "DENY")
		response.headers.setdefault("Referrer-Policy", "no-referrer")
		if request.url.scheme == "https":
			response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		return response


async def _seed_user(
	*,
	label: str,
	enabled: bool,
	update_existing: bool,
	email: str | None,
	password: str | None,
	role: UserRole,
) -> None:
	if not enabled:
		return
	if not email or not password:
		logger.warning("seed_user_missing_credentials", label=label)
		return

	normalized_email = email.strip().lower()
	if len(password) < 12:
		logger.warning("seed_user_password_too_short", label=label, email=normalized_email)
		return

	async with SessionLocal() as db:
		try:
			res = await db.execute(text("SELECT to_regclass('public.users')"))
			table = res.scalar_one_or_none()
			if table is None:
				logger.warning("seed_user_table_missing", label=label, table="users")
				return
		except SQLAlchemyError:
			logger.exception("seed_user_db_error", label=label)
			return

		existing = await db.scalar(select(User).where(User.email == normalized_email))
		if existing is not None:
			if not update_existing:
				logger.info("seed_user_exists", label=label, email=normalized_email)
				return

			existing.hashed_password = hash_password(password)
			existing.role = role
			existing.is_active = True
			await db.commit()
			logger.info("seed_user_updated", label=label, email=normalized_email, role=str(role))
			return
		user = User(
			email=normalized_email,
			hashed_password=hash_password(password),
			role=role,
			is_active=True,
		)
		db.add(user)
		await db.commit()
		logger.info("seed_user_created", label=label, email=normalized_email, role=str(role))


@asynccontextmanager
async def lifespan(_: FastAPI):
	await _seed_user(
		label="admin",
		enabled=settings.seed_admin,
		update_existing=settings.seed_admin_update_existing,
		email=settings.admin_email,
		password=settings.admin_password,
		role=UserRole.ADMIN,
	)
	await _seed_user(
		label="agent",
		enabled=settings.seed_agent,
		update_existing=settings.seed_agent_update_existing,
		email=settings.agent_email,
		password=settings.agent_password,
		role=UserRole.AGENT,
	)
	yield


app = FastAPI(title="Tickets API", version="0.1.0", lifespan=lifespan)

app.add_middleware(MetricsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)

if settings.cors_origins:
	app.add_middleware(
		CORSMiddleware,
		allow_origins=settings.cors_origins,
		allow_credentials=True,
		allow_methods=["*"],
		allow_headers=["*"],
	)

install_exception_handlers(app)

app.include_router(auth_router)
app.include_router(tickets_router)

app.mount("/metrics", make_asgi_app())


@app.get("/healthz")
async def healthz():
	return {"status": "ok"}


@app.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)):
	checks: dict[str, Any] = {"db": "ok", "redis": "ok"}
	ok = True

	try:
		res = await db.execute(text("SELECT 1"))
		res.scalar_one()
	except Exception:
		ok = False
		checks["db"] = "error"

	try:
		await redis_client.ping()
	except (RedisError, Exception):
		ok = False
		checks["redis"] = "error"

	status_code = HTTP_200_OK if ok else HTTP_503_SERVICE_UNAVAILABLE
	return ORJSONResponse(status_code=status_code, content={"status": "ok" if ok else "error", "checks": checks})


@app.get("/db-ping")
async def db_ping(db: AsyncSession = Depends(get_db)):
	result = await db.execute(text("SELECT 1"))
	return {"result": result.scalar_one()}

