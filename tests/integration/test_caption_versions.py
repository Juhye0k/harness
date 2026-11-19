"""Real DB version isolation, concurrent reuse, and auth/deletion boundaries."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.orm import Session

from app.adapters.caption_repository import CaptionRepository
from app.cli.cleanup_data import sweep
from app.models import AnalysisJob, Asset, CaptionRevision, HighlightCandidate, VideoJob, utcnow
from tests.integration.test_analysis_flow import BASE, submit
from tests.integration.test_auth_data import setup as auth_setup  # noqa: F401

pytestmark = [pytest.mark.integration]


@pytest.mark.skipif(os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture workers required")
def test_immutable_versions_confirmation_and_concurrent_render_reuse():
    with httpx.Client(base_url=BASE, timeout=20) as client:
        analysis = submit(client)
        aid = analysis["analysis_id"]
        cid, other_cid = [c["id"] for c in analysis["candidates"]]
        base = f"/analyses/{aid}/candidates/{cid}"
        editor = client.get(base + "/editor").json()
        assert editor["suggested"]["quality_pass"]
        body = {
            "source_version": editor["source_version"],
            "cues": editor["suggested"]["cues"],
            "reviewed": False,
        }
        # API accepts only the minimal editor schema, not provider/display internals.
        body["cues"] = [
            {k: c[k] for k in ("source_segment_id", "start_ms", "end_ms", "lines")}
            for c in body["cues"]
        ]
        saved = client.post(base + "/caption-revisions", json=body)
        assert saved.status_code == 201, saved.text
        rid = saved.json()["revision_id"]
        blocked = client.post(base + f"/caption-revisions/{rid}/exports", json={})
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "SUBTITLE_REVIEW_REQUIRED"
        assert client.get(base + f"/caption-revisions/{rid}").json()["render_job_id"] is None
        assert (
            client.post(
                base + "/caption-revisions", json={**body, "source_version": "wrong"}
            ).status_code
            == 409
        )
        assert (
            client.post(
                base + "/caption-revisions",
                json={**body, "cues": [body["cues"][0]], "reviewed": True},
            ).status_code
            == 422
        )
        assert client.post(base + "/caption-revisions", json=body).json()["revision_id"] == rid
        confirmed = client.post(base + "/caption-revisions", json={**body, "reviewed": True}).json()
        new_id = confirmed["revision_id"]
        assert new_id != rid
        assert client.get(base + f"/caption-revisions/{rid}").json()["reviewed"] is False
        foreign_revision = f"/analyses/{aid}/candidates/{other_cid}/caption-revisions/{new_id}"
        assert client.get(foreign_revision).status_code == 404
        assert client.post(foreign_revision + "/exports", json={}).status_code == 404
        repo = CaptionRepository()
        # Only one DB transaction may create the version-specific job. No messages are issued here.
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(lambda _: repo.export(UUID(aid), UUID(cid), UUID(new_id)), range(4))
            )
        assert sum(created for _, created in results) == 1
        assert len({job.id for job, _ in results}) == 1
        # Final rendering cannot collide with the original extraction's candidate uniqueness.
        original = client.post(base + "/exports").json()
        assert original["job_id"] != str(results[0][0].id)
        with Session(repo.engine) as s, s.begin():
            s.get(VideoJob, results[0][0].id).status = "failed"
        assert (
            client.post(base + f"/caption-revisions/{new_id}/exports", json={}).json()["status"]
            == "failed"
        )
        assert client.get(base + f"/caption-revisions/{new_id}").json()["render_job_id"] == str(
            results[0][0].id
        )


@pytest.mark.skipif(
    not os.getenv("AUTH_TEST_DATABASE_URL"), reason="Dedicated auth database required"
)
def test_caption_versions_respect_owner_expiry_and_asset_cleanup(auth_setup):  # noqa: F811
    client, engine, user, other, ids, root = auth_setup
    with Session(engine) as s, s.begin():
        asset = Asset(
            source_url="https://fixture.example/owned.mp4",
            user_id=user,
            legacy=False,
            expires_at=utcnow() + timedelta(days=7),
            state="succeeded",
        )
        s.add(asset)
        s.flush()
        asset_id = asset.id
        analysis = AnalysisJob(
            asset_id=asset.id,
            genre="unknown",
            purpose="balanced",
            config={"asr_version": "fixture"},
            status="succeeded",
        )
        s.add(analysis)
        s.flush()
        aid = analysis.id
        candidate = HighlightCandidate(
            analysis_id=aid,
            rank=1,
            data={
                "start_ms": 0,
                "end_ms": 10000,
                "title": "원본",
                "segments": [{"id": "s0", "text": "원본", "start_ms": 0, "end_ms": 1000}],
            },
        )
        s.add(candidate)
        s.flush()
        cid = candidate.id
    base = f"/analyses/{aid}/candidates/{cid}"
    body = {
        "source_version": "fixture",
        "reviewed": True,
        "cues": [
            {"source_segment_id": "s0", "start_ms": 0, "end_ms": 1000, "lines": ["수정 자막"]}
        ],
    }
    saved = client.post(base + "/caption-revisions", json=body)
    assert saved.status_code == 201, saved.text
    rid = saved.json()["revision_id"]
    foreign = f"/analyses/{ids['analysis']}/candidates/{cid}"
    assert client.get(foreign + "/editor").status_code == 404
    assert client.get(foreign + f"/caption-revisions/{rid}").status_code == 404
    assert client.post(foreign + "/caption-revisions", json=body).status_code == 404
    assert client.post(foreign + f"/caption-revisions/{rid}/exports", json={}).status_code == 404
    assert client.get(f"/analyses/{ids['analysis']}/source-video").status_code == 404
    assert client.get(base + f"/caption-revisions/{uuid4()}").status_code == 404
    # Asset deletion removes caption text with candidates; it cannot retain private revisions.
    assert client.delete(f"/assets/{asset_id}").status_code == 202
    assert client.get(base + f"/caption-revisions/{rid}").status_code == 410
    sweep(engine, root)
    with Session(engine) as s:
        assert s.get(CaptionRevision, UUID(rid)) is None
    # Cleanup removes the analysis row too, so its nested resource is now absent.
    assert client.get(base + f"/caption-revisions/{rid}").status_code == 404
