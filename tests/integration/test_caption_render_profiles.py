"""Versioned export reuse and compatibility against the migrated PostgreSQL schema."""

import os
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.adapters.caption_repository import CaptionRepository
from app.api import editor
from app.domain.portrait import EDITED_PROFILE, LEGACY_EDITED_PROFILE
from app.models import AnalysisJob, Asset, CaptionRevision, HighlightCandidate, VideoJob, utcnow
from tests.integration.test_auth_data import setup as auth_setup  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("AUTH_TEST_DATABASE_URL"), reason="Dedicated auth database required"
    ),
]


def test_profile_and_confirmed_spans_pin_jobs_without_obsoleting_legacy_download(
    auth_setup,  # noqa: F811
    monkeypatch,
):
    client, engine, user, _, _, root = auth_setup
    source_hash = "a" * 64
    cues = [{"source_segment_id": "s0", "start_ms": 1250, "end_ms": 2250, "lines": ["원본"]}]
    published = []
    monkeypatch.setattr(
        editor, "publish_video_job", lambda job_id, _: published.append(str(job_id))
    )
    (root / "legacy.mp4").write_bytes(b"legacy job's independent download")
    with Session(engine) as s, s.begin():
        asset = Asset(
            source_url="https://fixture.example/owned.mp4",
            user_id=user,
            legacy=False,
            expires_at=utcnow() + timedelta(days=7),
            state="succeeded",
            sha256=source_hash,
        )
        s.add(asset)
        s.flush()
        analysis = AnalysisJob(
            asset_id=asset.id,
            genre="unknown",
            purpose="balanced",
            config={"asr_version": "fixture"},
            status="succeeded",
        )
        s.add(analysis)
        s.flush()
        candidate = HighlightCandidate(
            analysis_id=analysis.id,
            rank=1,
            data={"start_ms": 1000, "end_ms": 4000, "segments": [{"id": "s0"}]},
        )
        old = VideoJob(
            source_url=asset.source_url,
            asset_id=asset.id,
            user_id=user,
            legacy=False,
            expires_at=asset.expires_at,
            start_seconds=1,
            duration_seconds=3,
            status="succeeded",
            output_path="legacy.mp4",
        )
        s.add_all([candidate, old])
        s.flush()
        revision = CaptionRevision(
            candidate_id=candidate.id,
            source_version="fixture",
            content_hash="b" * 64,
            cues=cues,
            reviewed=True,
            render_job_id=old.id,
        )
        s.add(revision)
        s.flush()
        base = f"/analyses/{analysis.id}/candidates/{candidate.id}/caption-revisions/{revision.id}"
        old_id = old.id

    assert client.get(base).json()["render_profile"] == LEGACY_EDITED_PROFILE
    assert client.get(base).json()["render_job_id"] == str(old_id)
    old_download = client.get(f"/jobs/{old_id}/download").content
    assert old_download == b"legacy job's independent download"
    reference_srt = client.get(f"/jobs/{old_id}/subtitles.srt").text
    assert "00:00:00,250 --> 00:00:01,250" in reference_srt
    url = base + "/exports"
    default = client.post(url, json={})
    assert default.status_code == 202, default.text
    default_id = default.json()["job_id"]
    assert default_id != str(old_id)
    assert default.json()["render_profile"] == EDITED_PROFILE
    assert client.post(url).json()["job_id"] == default_id

    def request(spans, source=source_hash):
        return client.post(
            url, json={"source_captions": {"source_sha256": source, "visible_spans": spans}}
        )

    spans = [{"start_ms": 1350, "end_ms": 1650}]
    assert request(spans, source="c" * 64).status_code == 409
    assert request([{"start_ms": 999, "end_ms": 1600}]).status_code == 422
    assert request([]).json()["job_id"] == default_id
    explicit = request(spans)
    assert explicit.status_code == 202, explicit.text
    explicit_id = explicit.json()["job_id"]
    assert explicit_id not in (default_id, str(old_id))
    assert (
        request([{"start_ms": 1350, "end_ms": 1500}, {"start_ms": 1500, "end_ms": 1650}]).json()[
            "job_id"
        ]
        == explicit_id
    )
    assert published == [default_id, explicit_id]
    latest = client.get(base).json()
    assert latest["render_job_id"] == explicit_id
    assert latest["render_profile"] == EDITED_PROFILE
    assert latest["source_caption_spans"] == spans
    assert latest["cues"] == cues and latest["reviewed"] is True

    default_result = client.get(base, params={"job": default_id}).json()
    assert default_result["render_job_id"] == default_id
    assert default_result["source_caption_spans"] == []
    unrelated = client.get(base, params={"job": str(uuid4())}).json()
    assert unrelated["render_job_id"] == explicit_id

    with Session(engine) as s, s.begin():
        assert s.get(CaptionRevision, UUID(latest["revision_id"])).render_job_id == old_id
        s.get(VideoJob, UUID(explicit_id)).status = "succeeded"
    repo = CaptionRepository(engine)
    assert repo.for_job(UUID(explicit_id))[0]["source_caption_spans"] == spans
    assert repo.for_job(UUID(default_id))[0]["source_caption_spans"] == []
    assert repo.for_job(old_id)[0]["render_profile"] == LEGACY_EDITED_PROFILE
    assert client.get(f"/jobs/{explicit_id}/subtitles.srt").text == reference_srt
    assert client.get(f"/jobs/{old_id}/download").content == old_download
