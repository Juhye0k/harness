import os

import pytest
from celery import Celery
from celery.result import AsyncResult
from fastapi.testclient import TestClient
from redis import Redis

from app.config import get_settings
from app.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1", reason="Set RUN_INTEGRATION=1 with services running"
    ),
]


def test_postgresql_and_redis_are_reachable():
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 200, response.json()


def test_worker_consumes_diagnostic_task():
    # A temporary Redis result backend is used ONLY for this diagnostic test.
    # Product job state will live in PostgreSQL, not Celery's result backend.
    diagnostic_app = Celery(
        "diagnostic-test", broker=get_settings().redis_url, backend=get_settings().redis_url
    )
    diagnostic_app.conf.task_default_queue = "shortform"
    result = diagnostic_app.send_task("shortform.diagnostics.ping", ignore_result=False)
    try:
        assert AsyncResult(result.id, app=diagnostic_app).get(timeout=30) == {"status": "ok"}
    finally:
        with Redis.from_url(get_settings().redis_url) as redis:
            redis.delete(f"celery-task-meta-{result.id}")
        diagnostic_app.close()
