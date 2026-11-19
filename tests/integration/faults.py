"""Fixture-only fault points. IDs and counters are scoped to an isolated Redis project."""

import time

from redis import Redis

from app.config import get_settings
from app.domain.video import VideoError


class Faults:
    def __init__(self, resource_id):
        settings = get_settings()
        if settings.app_env != "test":
            raise RuntimeError("Fault controls are test-only")
        self.url = settings.redis_url
        self.key = f"failure:{resource_id}"

    def connection(self):
        return Redis.from_url(
            self.url, decode_responses=True, socket_connect_timeout=2, socket_timeout=3
        )

    def hit(self, stage):
        with self.connection() as redis:
            redis.hincrby(self.key + ":events", stage, 1)

    def point(self, stage):
        self.hit(stage)
        with self.connection() as redis:
            config = redis.hgetall(self.key + ":config")
            if config.get("pause_at") == stage:
                redis.hset(self.key + ":events", "paused", stage)
                redis.rpush(self.key + ":ready", stage)
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if redis.blpop(self.key + ":release", timeout=1):
                        break
                else:
                    raise VideoError("TIMEOUT", "fixture barrier timed out")
        if config.get("fail_at") == stage:
            code = config.get("code", "TOOL_FAILED")
            if code not in {
                "PROVIDER_ACCESS_DENIED",
                "RATE_LIMITED",
                "TIMEOUT",
                "TOOL_FAILED",
                "FONT_MISSING",
                "OUTPUT_INVALID",
                "DISPATCH_FAILED",
            }:
                raise RuntimeError("Unsupported fixture fault")
            raise VideoError(code, "private-fixture-sentinel")


def install_analysis_faults(analysis, fixture_type):
    from app.adapters.analysis_repository import AnalysisRepository

    claim, process = AnalysisRepository.claim, analysis.process_analysis

    def instrumented_claim(repo, job_id):
        job = claim(repo, job_id)
        if job:
            Faults(job_id).point("analysis-claim")
        return job

    class FaultProviders(fixture_type):
        def __init__(self, settings, fault):
            super().__init__(settings)
            self.fault = fault

        def transcribe(self, audio):
            self.fault.point("transcription")
            return super().transcribe(audio)

        def recommend(self, stage, payload, model):
            self.fault.point(stage)
            return super().recommend(stage, payload, model)

    def instrumented_process(job_id, repo, root, settings, providers=None):
        return process(
            job_id,
            repo,
            root,
            settings,
            providers=providers or FaultProviders(settings, Faults(job_id)),
        )

    AnalysisRepository.claim = instrumented_claim
    analysis.process_analysis = instrumented_process


def install_video_faults():
    from app.adapters.job_repository import JobRepository
    from app.services import final_export

    claim, execute = JobRepository.claim, final_export.execute_final

    def instrumented_claim(repo, job_id):
        job = claim(repo, job_id)
        if job:
            Faults(job_id).point("video-claim")
        return job

    def instrumented_render(asset, job, revision, root, data_root):
        Faults(job.id).point("render")
        return execute(asset, job, revision, root, data_root)

    JobRepository.claim = instrumented_claim
    final_export.execute_final = instrumented_render


def fixture_publish(job_id, task_id):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.adapters.job_publisher import publish_analysis_job
    from app.db import get_engine
    from app.models import AnalysisRequestReceipt

    fault = Faults(job_id)
    with Session(get_engine()) as session:
        request_id = session.scalar(
            select(AnalysisRequestReceipt.request_id).where(
                AnalysisRequestReceipt.analysis_id == job_id
            )
        )
    if request_id:
        with fault.connection() as redis:
            config = redis.hgetall(f"failure-request:{request_id}")
            if config:
                redis.hset(fault.key + ":config", mapping=config)
    fault.point("publish")
    publish_analysis_job(job_id, task_id)
    fault.point("after-publish")


def fixture_video_publish(job_id, task_id):
    from app.adapters.caption_repository import CaptionRepository
    from app.adapters.job_publisher import publish_video_job

    fault = Faults(job_id)
    revision = CaptionRepository().for_job(job_id)
    if revision:
        revision_id = revision[0]["revision_id"]
        with fault.connection() as redis:
            config = redis.hgetall(f"failure-revision:{revision_id}")
            if config:
                redis.hset(fault.key + ":config", mapping=config)
    publish_video_job(job_id, task_id)
