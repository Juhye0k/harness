"""Real PostgreSQL concurrency checks. Remove only rows created by each test."""

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Barrier, Event

import pytest
from sqlalchemy import delete

from app.adapters.job_repository import JobRepository
from app.models import VideoJob
from app.services.jobs import process_job

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1", reason="Dedicated infrastructure required"
    ),
]


@pytest.fixture
def stored_job():
    repo = JobRepository()
    job = repo.create("https://fixture.example/sample.mp4", 0)
    yield repo, job
    with repo.engine.begin() as connection:
        connection.execute(delete(VideoJob).where(VideoJob.id == job.id))


def test_only_one_worker_claims(stored_job):
    repo, job = stored_job
    repo.dispatch(job.id, lambda *a: None)
    barrier = Barrier(2)

    def claim():
        barrier.wait(timeout=5)
        return repo.claim(job.id)

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(claim) for _ in range(2)]
        claimed = [f.result(timeout=10) for f in futures]
    assert sum(value is not None for value in claimed) == 1
    assert repo.get(job.id).status == "running"


@pytest.mark.parametrize("publish_fails", [False, True])
def test_worker_waits_for_publish_commit(stored_job, publish_fails):
    repo, job = stored_job
    entered = Event()
    with ThreadPoolExecutor(1) as pool:
        received = []

        def claim():
            entered.set()
            return repo.claim(job.id)

        def publish(*args):
            future = pool.submit(claim)
            received.append(future)
            assert entered.wait(timeout=5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.2)
            if publish_fails:
                raise ConnectionError("message may already be delivered")

        published = repo.dispatch(job.id, publish)
        claimed = received[0].result(timeout=10)
    assert published.status == ("failed" if publish_fails else "queued")
    assert (claimed is None) == publish_fails
    assert repo.get(job.id).status == ("failed" if publish_fails else "running")


def test_manual_failure_blocks_late_completion(stored_job):
    repo, job = stored_job
    repo.dispatch(job.id, lambda *a: None)
    repo.claim(job.id)
    assert repo.mark_interrupted(job.id, "worker stopped")
    assert not repo.finish(job.id, success=True, output_path="late.mp4")
    assert repo.get(job.id).error_code == "INTERRUPTED"


def test_manual_failure_cannot_replace_success(stored_job):
    repo, job = stored_job
    repo.dispatch(job.id, lambda *a: None)
    repo.claim(job.id)
    assert repo.finish(job.id, success=True, output_path="clip.mp4")
    assert not repo.mark_interrupted(job.id, "too late")
    assert repo.get(job.id).status == "succeeded"


def test_completion_and_manual_failure_race(stored_job):
    repo, job = stored_job
    repo.dispatch(job.id, lambda *a: None)
    repo.claim(job.id)
    barrier = Barrier(2)

    def complete():
        barrier.wait(timeout=5)
        return repo.finish(job.id, success=True, output_path="clip.mp4")

    def fail():
        barrier.wait(timeout=5)
        return repo.mark_interrupted(job.id, "operator confirmed")

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(complete), pool.submit(fail)]
        assert sum(f.result(timeout=10) for f in futures) == 1
    assert repo.get(job.id).status in {"succeeded", "failed"}


def test_processing_failure_is_persisted(stored_job, tmp_path):
    repo, job = stored_job
    repo.dispatch(job.id, lambda *a: None)
    process_job(
        job.id,
        repo,
        tmp_path,
        extractor=lambda *a, **kw: {
            "status": "failed",
            "error": {"code": "TOOL_FAILED", "message": "private"},
        },
    )
    persisted = repo.get(job.id)
    assert persisted.status == "failed" and persisted.error_code == "TOOL_FAILED"
    assert "private" not in persisted.error_message
