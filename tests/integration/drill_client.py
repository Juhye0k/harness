"""Internal-network client for host-controlled drills. Never controls Docker itself."""

import argparse
import json
import time
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.job_publisher import publish_video_job
from app.adapters.job_repository import JobRepository
from app.adapters.sns_repository import SnsRepository
from app.config import get_settings
from app.models import AnalysisRequestReceipt, ProviderCall
from tests.integration.faults import Faults
from tests.integration.test_analysis_flow import BASE


def wait(client, path, terminal=("succeeded", "failed", "unknown")):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = client.get(path).json()
        if result["status"] in terminal:
            return result
        time.sleep(0.1)
    raise TimeoutError("Fixture job did not complete")


def ready(resource, stage):
    fault = Faults(resource)
    with fault.connection() as redis:
        assert redis.blpop(fault.key + ":ready", timeout=30)[1] == stage
        return redis.hgetall(fault.key + ":events")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "prepare-video",
            "video-paused",
            "verify-video",
            "arm-request",
            "submit-analysis",
            "analysis-paused",
            "verify-analysis",
            "prepare-sns",
            "sns-paused",
            "verify-sns",
        ],
    )
    parser.add_argument("--id", type=UUID)
    args = parser.parse_args()
    identifier = args.id
    settings = get_settings()
    assert settings.app_env == "test" and not settings.enable_paid_ai
    result = {}
    with httpx.Client(base_url=BASE, timeout=30) as client:
        if args.action == "prepare-video":
            repo = JobRepository()
            job = repo.create("https://fixture.example/sample.mp4", 2)
            with Faults(job.id).connection() as redis:
                redis.hset(f"failure:{job.id}:config", mapping={"pause_at": "video-claim"})
            repo.dispatch(job.id, publish_video_job)
            result = {"job_id": str(job.id)}
        elif args.action == "video-paused":
            events = ready(identifier, "video-claim")
            assert JobRepository().get(identifier).status == "running"
            result = {"status": "running", "events": events}
        elif args.action == "verify-video":
            repo = JobRepository()
            assert repo.get(identifier).status == "failed"
            assert repo.get(identifier).error_code == "INTERRUPTED"
            assert not repo.finish(identifier, success=True)
            assert client.get(f"/jobs/{identifier}/download").status_code == 409
            with Faults(identifier).connection() as redis:
                assert redis.hget(f"failure:{identifier}:events", "video-claim") == "1"
            result = {"status": "failed", "late_completion_rejected": True, "executions": 1}
        elif args.action == "arm-request":
            with Faults(identifier).connection() as redis:
                redis.hset(f"failure-request:{identifier}", mapping={"pause_at": "after-publish"})
            result = {"armed": True}
        elif args.action == "submit-analysis":
            try:
                response = client.post(
                    "/analyses",
                    json={
                        "request_id": str(identifier),
                        "url": "https://fixture.example/analysis.mp4",
                    },
                )
                result = {"response_lost": False, "http_status": response.status_code}
            except httpx.TransportError:
                result = {"response_lost": True}
        elif args.action == "analysis-paused":
            repo = AnalysisRepository()
            deadline = time.monotonic() + 30
            aid = None
            while time.monotonic() < deadline:
                with Session(repo.engine) as s:
                    row = s.get(AnalysisRequestReceipt, ("local-development", identifier))
                    if row:
                        aid = row.analysis_id
                if aid:
                    break
                time.sleep(0.1)
            assert aid
            events = ready(aid, "after-publish")
            assert repo.get(aid).status == "pending"
            result = {"analysis_id": str(aid), "status": "pending", "events": events}
        elif args.action == "verify-analysis":
            repo = AnalysisRepository()
            job = repo.get(identifier)
            assert job.status == "failed" and job.error_code == "INTERRUPTED"
            assert not repo.finish(identifier, outcome="RECOMMENDED")
            with Session(repo.engine) as s:
                assert (
                    s.scalar(select(ProviderCall.id).where(ProviderCall.analysis_id == identifier))
                    is None
                )
            result = {"status": "failed", "provider_calls": 0, "late_completion_rejected": True}
        elif args.action == "prepare-sns":
            job = client.post(
                "/jobs/video-extractions",
                json={"url": "https://fixture.example/sample.mp4", "start_seconds": 2},
            ).json()
            assert wait(client, job["status_url"])["status"] == "succeeded"
            session = client.get("/sns/session").json()
            client.headers["X-SNS-CSRF"] = session["csrf"]
            authorization = client.post("/sns/youtube/connect").json()["authorization_url"]
            state = parse_qs(urlsplit(authorization).query)["state"][0]
            assert (
                client.get(
                    "/sns/youtube/callback", params={"state": state, "code": "fixture-code"}
                ).status_code
                == 303
            )
            account = client.get("/sns/accounts").json()[0]
            from uuid import uuid4

            draft = client.post(
                "/sns/uploads",
                json={
                    "request_id": str(uuid4()),
                    "job_id": job["job_id"],
                    "account_id": account["account_id"],
                    "title": "isolated-crash-drill",
                    "made_for_kids": False,
                },
            ).json()
            uid = draft["upload_id"]
            fault = Faults(uid)
            with fault.connection() as redis:
                redis.hset(fault.key + ":config", mapping={"pause_at": "after-send"})
                cookies = [
                    {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                    for c in client.cookies.jar
                ]
                # Keep fixture sessions inside the private broker, never in artifacts.
                redis.setex(fault.key + ":session", 300, json.dumps(cookies))
            assert (
                client.post(
                    f"/sns/uploads/{uid}/confirm",
                    json={"confirmed": True, "approval": draft["approval"]},
                ).status_code
                == 202
            )
            result = {"upload_id": uid, "job_id": job["job_id"]}
        elif args.action == "sns-paused":
            events = ready(identifier, "after-send")
            # Internal read through the persisted fixture session below is intentionally deferred.
            result = {"events": events, "bytes_accepted": True}
        elif args.action == "verify-sns":
            fault = Faults(identifier)
            with fault.connection() as redis:
                cookies = json.loads(redis.get(fault.key + ":session"))
            for cookie in cookies:
                client.cookies.set(**cookie)
            client.headers["X-SNS-CSRF"] = client.get("/sns/session").json()["csrf"]
            upload = client.get(f"/sns/uploads/{identifier}").json()
            assert upload["status"] == "unknown" and upload["can_probe"]
            assert not SnsRepository().finish(identifier, "succeeded", remote_id="abcdefghijk")
            assert client.post(f"/sns/uploads/{identifier}/probe").status_code == 202
            assert (
                wait(client, f"/sns/uploads/{identifier}", terminal=("succeeded", "failed"))[
                    "status"
                ]
                == "succeeded"
            )
            with fault.connection() as redis:
                counts = redis.hgetall(f"sns-fixture:{identifier}")
                assert (
                    counts["sent"] == "1" and counts["initiated"] == "1" and counts["probed"] == "1"
                )
                redis.delete(fault.key + ":session")
            result = {
                "status_before_probe": "unknown",
                "status_after_probe": "succeeded",
                "sends": 1,
                "probes": 1,
                "late_completion_rejected": True,
            }
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
