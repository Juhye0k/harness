import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.auth_middleware import AuthMiddleware
from app.adapters.sns_logging import install_sns_logging
from app.api.analyses import router as analysis_router
from app.api.auth import router as auth_router
from app.api.data import router as data_router
from app.api.jobs import router
from app.api.sns import router as sns_router
from app.api.transcript_review import router as review_router
from app.api.verification import router as verification_router
from app.api.web import STATIC
from app.api.web import router as web_router
from app.auth_models import User  # noqa: F401
from app.config import get_settings
from app.db import check_database
from app.domain.jobs import JobError
from app.domain.sns import SnsError
from app.domain.video import VideoError

logger = logging.getLogger(__name__)
install_sns_logging()
app = FastAPI(title="Shortform Harness", version="0.1.0")
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)
app.include_router(data_router)
app.include_router(router)
app.include_router(analysis_router)
app.include_router(sns_router)
app.include_router(review_router)
app.include_router(web_router)
app.include_router(verification_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def sns_private_response(request, call_next):
    response = await call_next(request)
    if request.url.path == "/sns" or request.url.path.startswith("/sns/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
    return response


@app.exception_handler(SnsError)
async def sns_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.code, "message": str(exc)},
        },
    )


@app.exception_handler(JobError)
async def job_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {"code": exc.code, "message": str(exc)},
            "job_id": str(exc.job_id) if exc.job_id else None,
        },
    )


@app.exception_handler(VideoError)
@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    if request.url.path.startswith("/sns/"):
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": "INVALID_INPUT", "message": "SNS 입력과 확인 내용을 확인하세요."},
            },
        )
    return JSONResponse(
        status_code=422,
        content={
            "error": {"code": "INVALID_INPUT", "message": "영상 URL과 시작 시간을 확인하세요."},
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "DATABASE_UNAVAILABLE",
                "message": "작업 저장소를 사용할 수 없습니다.",
            },
        },
    )


def check_redis() -> None:
    with Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=3, socket_timeout=3
    ) as client:
        client.ping()


@app.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    """Process health only; no infrastructure or model requests."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready() -> JSONResponse:
    """DB and broker connectivity only. This does not check worker availability."""
    checks = {}
    for name, probe in (("postgresql", check_database), ("redis", check_redis)):
        try:
            probe()
            checks[name] = "ok"
        except Exception as exc:
            # Do not expose connection URLs, credentials, or raw driver messages.
            logger.warning("Readiness probe failed: %s (%s)", name, type(exc).__name__)
            checks[name] = "unavailable"
    is_ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "unavailable", "checks": checks},
    )
