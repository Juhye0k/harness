from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.analyses import repository
from app.domain.recommendations import normalize
from app.domain.transcript_review import inspect, quality
from app.main import app


def segment(**kwargs):
    return {"id": "s0", "text": "내용 확인", "start_ms": 0, "end_ms": 2000, **kwargs}


def test_thresholds_and_legacy_are_not_accuracy_claims():
    legacy = segment()
    raw = [
        legacy,
        segment(
            id="s1",
            start_ms=2000,
            end_ms=4000,
            quality={"avg_logprob": -1.01, "no_speech_prob": 0.61},
        ),
    ]
    before = deepcopy(raw)
    result = inspect(raw)
    assert result["quality_available"] == 1 and raw == before
    assert result["segments"][0]["recognition_reasons"] == [
        "LOW_CONFIDENCE",
        "POSSIBLE_NON_SPEECH",
        "ADJACENT_REPETITION",
    ]
    assert inspect([legacy])["flagged"] == 0
    assert inspect([segment(quality={"avg_logprob": -1, "compression_ratio": 2.4})])["flagged"] == 0
    assert inspect([])["total"] == 0


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"avg_logprob": float("nan")},
        {"no_speech_prob": True},
        {"no_speech_prob": 2},
        {"compression_ratio": -1},
        {"avg_logprob": 1},
        {"avg_logprob": "-2"},
    ],
)
def test_missing_invalid_quality_is_unavailable(value):
    assert quality(value) == {}


def test_quality_survives_normalization_and_sampling_is_repeatable():
    raw = {
        "phrases": [
            {
                "text": "내용",
                "offsetMilliseconds": 0,
                "durationMilliseconds": 2000,
                "quality": {"avg_logprob": -1.5},
            }
        ]
    }
    normalized = normalize(raw, 2000)
    assert normalized[0]["quality"] == {"avg_logprob": -1.5}
    rows = [
        segment(id=f"s{i}", text=f"내용 {i}", start_ms=i * 2000, end_ms=i * 2000 + 2000)
        for i in range(10)
    ]
    assert inspect(rows)["unflagged_sample_ids"] == inspect(rows)["unflagged_sample_ids"]
    assert len(inspect(rows)["unflagged_sample_ids"]) == 5


def test_api_incomplete_does_not_read_or_write():
    app.dependency_overrides[repository] = lambda: SimpleNamespace(
        get=lambda _: SimpleNamespace(status="running")
    )
    try:
        with TestClient(app) as client:
            for suffix in ["transcript-review", "review-audio"]:
                assert client.get(f"/analyses/{uuid4()}/{suffix}").status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_version_segment_validation_and_readonly_report():
    identifier = uuid4()
    job = SimpleNamespace(
        id=identifier, asset_id=uuid4(), status="succeeded", config={"asr_version": "legacy"}
    )
    repo = SimpleNamespace(
        get=lambda _: job, read_transcript=lambda *_: [segment()], review_decisions=lambda *_: {}
    )
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as client:
            base = f"/analyses/{identifier}/transcript-review"
            result = client.get(base).json()
            assert result["unreviewed"] == 1
            body = {
                "transcript_version": "wrong",
                "policy_version": result["policy_version"],
                "decision": "ok",
                "revision": 0,
            }
            assert client.put(base + "/s0", json=body).status_code == 409
            assert client.put(base + "/missing", json=body).status_code == 404
            body["decision"] = "automatic correction"
            assert client.put(base + "/s0", json=body).status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("version", ["..", "../secret", "C:\\secret", "valid-version"])
def test_audio_missing_or_unsafe_version_never_reads_other_files(tmp_path, monkeypatch, version):
    from app.api import transcript_review

    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic source")
    repo = SimpleNamespace(
        get=lambda _: SimpleNamespace(
            status="succeeded",
            asset_id=uuid4(),
            config={"asr_version": version, "transcription_provider": "groq"},
        ),
        read_transcript=lambda *_: [segment()],
        asset=lambda _: SimpleNamespace(path="source.mp4"),
    )
    monkeypatch.setattr(
        transcript_review, "get_settings", lambda: SimpleNamespace(video_data_dir=tmp_path)
    )
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as client:
            assert client.get(f"/analyses/{uuid4()}/review-audio").status_code == 404
    finally:
        app.dependency_overrides.clear()
