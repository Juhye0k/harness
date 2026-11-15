import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy.exc import SQLAlchemyError

from app.api.jobs import router
from app.config import get_settings
from app.db import check_database
from app.domain.jobs import JobError
from app.domain.video import VideoError

logger = logging.getLogger(__name__)
app = FastAPI(title="Shortform Harness", version="0.1.0")
app.include_router(router)


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
