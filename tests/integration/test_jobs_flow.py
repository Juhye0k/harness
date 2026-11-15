"""HTTP through the real container API, Redis, worker and shared output volume."""

import os
import time
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.job_publisher import publish_video_job
from app.adapters.job_repository import JobRepository
from app.api.jobs import publisher
from app.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_VIDEO_INTEGRATION") != "1",
        reason="Dedicated fixture worker required",
    ),
]


@pytest.fixture
def client():
    with httpx.Client(base_url=os.getenv("TEST_API_URL", "http://api:8000"), timeout=15) as client:
        yield client


def wait_for_job(client, job_id):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.2)
    pytest.fail("Video job did not reach a terminal state")


def submit(client, start=5, filename="sample.mp4"):
    response = client.post(
        "/jobs/video-extractions",
        json={
            "url": f"https://fixture.example/{filename}",
            "start_seconds": start,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


def test_complete_video_flow_and_duplicate_delivery(client):
    job_id = submit(client)
    job = wait_for_job(client, job_id)
    assert job["status"] == "succeeded", job
    assert all(job["result"]["checks"].values())
    assert abs(job["result"]["media"]["duration"] - 10) <= 0.1
    download = client.get(job["download_url"])
    assert download.status_code == 200 and download.headers["content-type"] == "video/mp4"
    assert download.content[4:8] == b"ftyp"
    repo = JobRepository()
    before = repo.get(UUID(job_id))
    publish_video_job(UUID(job_id), uuid4())
    # A following job completing on the single worker proves the duplicate was consumed.
    assert wait_for_job(client, submit(client))["status"] == "succeeded"
    after = repo.get(UUID(job_id))
    assert (after.run_id, after.finished_at) == (before.run_id, before.finished_at)


@pytest.mark.parametrize(
    "start,filename,code",
    [
        (19, "sample.mp4", "INVALID_RANGE"),
        (0, "tool-failure.mp4", "TOOL_FAILED"),
    ],
)
def test_failed_job_is_queryable_and_not_downloadable(client, start, filename, code):
    job_id = submit(client, start, filename)
    job = wait_for_job(client, job_id)
    assert job["status"] == "failed" and job["error"]["code"] == code
    assert client.get(f"/jobs/{job_id}/download").status_code == 409


def test_dispatch_failure_is_recorded():
    def failed_publish(*args):
        raise ConnectionError("private connection info")

    app.dependency_overrides[publisher] = lambda: failed_publish
    try:
        with TestClient(app) as client:
            response = client.post(
                "/jobs/video-extractions",
                json={
                    "url": "https://fixture.example/sample.mp4",
                    "start_seconds": 0,
                },
            )
            assert response.status_code == 503
            assert "private" not in response.text
            job = client.get(f"/jobs/{response.json()['job_id']}").json()
            assert job["status"] == "failed" and job["error"]["code"] == "DISPATCH_FAILED"
    finally:
        app.dependency_overrides.clear()
