import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from redis import Redis

from app.config import get_settings
from app.db import check_database

logger = logging.getLogger(__name__)
app = FastAPI(title="Shortform Harness", version="0.1.0")


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
