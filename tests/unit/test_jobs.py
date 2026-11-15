from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.jobs import publisher, repository
from app.config import get_settings
from app.domain.jobs import JobError, output_file, public_result
from app.main import app
from app.services.jobs import process_job


class FakeRepository:
    def __init__(self, status="queued"):
        self.job = SimpleNamespace(
            id=uuid4(),
            task_id=uuid4(),
            source_url="https://example.com/a?token=secret",
            start_seconds=5,
            duration_seconds=10,
            status=status,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            started_at=None,
            finished_at=None,
            error_code=None,
            error_message=None,
            result=None,
            output_path=None,
        )
        self.finishes = []

    def create(self, url, start):
        self.job.source_url, self.job.start_seconds = url, start
        return self.job

    def dispatch(self, job_id, publish):
        publish(job_id, self.job.task_id)
        self.job.status = "queued"
        return self.job

    def get(self, job_id):
        return self.job

    def claim(self, job_id):
        if self.job.status != "queued":
            return None
        self.job.status = "running"
        return self.job

    def finish(self, job_id, **values):
        self.finishes.append(values)
        return True


@pytest.fixture
def client():
    repo = FakeRepository()
    sent = []
    app.dependency_overrides[repository] = lambda: repo
    app.dependency_overrides[publisher] = lambda: lambda *ids: sent.append(ids)
    with TestClient(app) as client:
        yield client, repo, sent
    app.dependency_overrides.clear()


def test_submit_returns_id_without_encoding(client, monkeypatch):
    client, repo, sent = client
    monkeypatch.setattr(
        "app.services.jobs.execute", lambda *a, **kw: pytest.fail("API encoded video")
    )
    response = client.post(
        "/jobs/video-extractions", json={"url": "https://example.com/a", "start_seconds": 5}
    )
    assert response.status_code == 202
    assert response.json()["job_id"] == str(repo.job.id)
    assert sent == [(repo.job.id, repo.job.task_id)]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"url": "https://example.com", "start_seconds": -1},
        {"url": "https://user:secret@example.com", "start_seconds": 0},
        {"url": "file:///secret", "start_seconds": 0},
        {"url": "https://example.com", "start_seconds": "nan"},
    ],
)
def test_api_invalid_input_is_sanitized(client, body):
    client, _, sent = client
    response = client.post("/jobs/video-extractions", json=body)
    assert response.status_code == 422
    assert "secret" not in response.text
    assert not sent


def test_query_omits_source_and_server_paths(client):
    client, repo, _ = client
    repo.job.output_path = "/private/path.mp4"
    response = client.get(f"/jobs/{repo.job.id}")
    assert response.status_code == 200
    assert "secret" not in response.text and "private" not in response.text
    assert response.json()["download_url"] is None


def test_db_error_is_sanitized(client, monkeypatch):
    client, repo, _ = client

    def fail(*args):
        raise OperationalError("secret", {}, Exception("password"))

    monkeypatch.setattr(repo, "get", fail)
    response = client.get(f"/jobs/{repo.job.id}")
    assert response.status_code == 503
    assert "secret" not in response.text and "password" not in response.text


@pytest.mark.parametrize("status", ["pending", "queued", "running", "failed"])
def test_download_before_success_is_rejected(client, status):
    client, repo, _ = client
    repo.job.status = status
    assert client.get(f"/jobs/{repo.job.id}/download").status_code == 409


def test_missing_download_is_gone(client):
    client, repo, _ = client
    repo.job.status = "succeeded"
    assert client.get(f"/jobs/{repo.job.id}/download").status_code == 410


def test_safe_download(client, tmp_path):
    client, repo, _ = client
    (tmp_path / "clip.mp4").write_bytes(b"sample")
    settings = get_settings()
    old = settings.video_data_dir
    try:
        settings.video_data_dir = tmp_path
        repo.job.status, repo.job.output_path = "succeeded", "clip.mp4"
        response = client.get(f"/jobs/{repo.job.id}/download")
        assert response.status_code == 200 and response.content == b"sample"
    finally:
        settings.video_data_dir = old


@pytest.mark.parametrize("path", ["../outside.mp4", "/etc/passwd", None])
def test_result_path_escape_is_rejected(tmp_path, path):
    with pytest.raises(JobError) as error:
        output_file(tmp_path, path)
    assert error.value.status_code == 410


def test_result_allowlist():
    result = public_result(
        {
            "output_path": "private",
            "source_url": "secret",
            "checks": {"url": "secret"},
            "media": {"path": "private"},
        }
    )
    assert result == {"checks": {}, "media": {}}


@pytest.mark.parametrize("state", ["running", "succeeded", "failed", "pending"])
def test_duplicate_does_not_execute(tmp_path, state):
    repo = FakeRepository(state)
    process_job(
        repo.job.id, repo, tmp_path, extractor=lambda *a, **kw: pytest.fail("duplicate ran")
    )
    assert not repo.finishes


def test_worker_maps_failure_without_raw_message(tmp_path):
    repo = FakeRepository()
    process_job(
        repo.job.id,
        repo,
        tmp_path,
        extractor=lambda *a, **kw: {
            "status": "failed",
            "error": {"code": "INVALID_RANGE", "message": "secret"},
        },
    )
    assert repo.finishes[0]["error_code"] == "INVALID_RANGE"
    assert "secret" not in str(repo.finishes)


@pytest.mark.parametrize(
    "exception,code",
    [(RuntimeError("secret"), "INTERNAL_ERROR"), (SoftTimeLimitExceeded(), "TIMEOUT")],
)
def test_worker_catches_exceptions(tmp_path, exception, code):
    repo = FakeRepository()

    def fail(*args, **kwargs):
        raise exception

    process_job(repo.job.id, repo, tmp_path, extractor=fail)
    assert repo.finishes[0]["error_code"] == code
    assert "secret" not in str(repo.finishes)


def test_unvalidated_output_cannot_succeed(tmp_path):
    repo = FakeRepository()
    process_job(
        repo.job.id,
        repo,
        tmp_path,
        extractor=lambda *a, **kw: {"status": "succeeded", "checks": {}},
    )
    assert repo.finishes[0]["success"] is False
