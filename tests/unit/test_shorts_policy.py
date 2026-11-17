from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.analyses import repository
from app.domain.shorts_subtitles import build_shorts
from app.domain.subtitles import compact
from app.main import app


def sample():
    words = ["오늘은", "좋은", "날입니다.", "함께", "해봐요."]
    return {
        "id": "s0",
        "text": " ".join(words),
        "start_ms": 0,
        "end_ms": 4000,
        "words": [
            {"text": w, "start_ms": i * 800, "end_ms": i * 800 + 700} for i, w in enumerate(words)
        ],
    }


def test_short_policy_preserves_words_and_all_constraints():
    source = sample()
    before = deepcopy(source)
    data = build_shorts([source])
    assert data["quality_pass"] and source == before
    assert len(data["cues"]) >= 3
    assert compact("".join(c["text"] for c in data["cues"])) == compact(source["text"])
    for cue in data["cues"]:
        duration = cue["end_ms"] - cue["start_ms"]
        assert 450 <= duration <= 1800
        assert len(cue["lines"]) <= 2 and all(len(line) <= 14 for line in cue["lines"])
        assert len(cue["text"]) * 1000 <= duration * 15
        assert 1 <= cue["eojeol_count"] <= 3


def test_twenty_one_seconds_and_nine_lines_are_blocked_not_emitted():
    source = {"id": "s0", "text": "긴 문장 " * 40, "start_ms": 0, "end_ms": 21483}
    data = build_shorts([source])
    assert not data["quality_pass"] and not data["cues"]
    assert data["blocked_segments"][0]["text"] == source["text"]


@pytest.mark.parametrize("duration", [200, 5000])
def test_unfixable_duration_does_not_invent_timestamps(duration):
    s = {
        "id": "s0",
        "text": "안녕",
        "start_ms": 0,
        "end_ms": duration,
        "words": [{"text": "안녕", "start_ms": 0, "end_ms": duration}],
    }
    assert not build_shorts([s])["quality_pass"]


def test_subword_tokens_are_not_split_inside_eojeol():
    s = {
        "id": "s0",
        "text": "안녕하세요.",
        "start_ms": 0,
        "end_ms": 1200,
        "words": [
            {"text": "안녕", "start_ms": 0, "end_ms": 500},
            {"text": "하세요.", "start_ms": 500, "end_ms": 1200},
        ],
    }
    assert [c["text"] for c in build_shorts([s])["cues"]] == ["안녕하세요."]


def test_invalid_timing_overlap_and_empty_are_not_ready():
    s = sample()
    s["words"][1]["start_ms"] = 1
    assert not build_shorts([s])["quality_pass"]
    assert not build_shorts([])["quality_pass"]
    assert not build_shorts([sample(), sample()])["quality_pass"]


def test_range_must_be_paired_and_cannot_cut_cue():
    with pytest.raises(ValueError):
        build_shorts([sample()], 1)
    assert not build_shorts([sample()], 100, 4000)["quality_pass"]


def test_api_legacy_compatibility_and_server_side_gate():
    aid, asset = uuid4(), uuid4()
    job = SimpleNamespace(
        id=aid, asset_id=asset, status="succeeded", config={"asr_version": "test"}
    )
    segments = [sample(), {"id": "s1", "text": "확인 필요", "start_ms": 5000, "end_ms": 26000}]
    repo = SimpleNamespace(
        get=lambda _: job,
        read_transcript=lambda *_: segments,
        review_decisions=lambda *_: {},
        asset=lambda *_: SimpleNamespace(duration_ms=30000),
    )
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as c:
            assert c.get(f"/analyses/{aid}/subtitles.srt").status_code == 200
            assert (
                c.get(f"/analyses/{aid}/subtitles.srt?profile=shorts-display-v1").status_code == 409
            )
            assert (
                c.get(
                    f"/analyses/{aid}/subtitles.srt?profile=shorts-display-v1&start_ms=0&end_ms=4000"
                ).status_code
                == 200
            )
            assert c.get(f"/analyses/{aid}/subtitles?profile=unknown").status_code == 422
            r = c.get(f"/analyses/{aid}/verification").json()
            assert not r["display"]["quality_pass"] and r["cer"] is None
            assert r["transcript_human_review"]["status"] == "pending"
    finally:
        app.dependency_overrides.clear()


def test_stale_code_record_is_not_a_pass(tmp_path, monkeypatch):
    import json

    from app.adapters.verification_record import code_status

    path = tmp_path / "record.json"
    path.write_text(
        json.dumps({"app_sha256": "old", "checks": {"basic": True, "integration": True}})
    )
    monkeypatch.setenv("VERIFICATION_RECORD", str(path))
    assert code_status()["status"] == "stale"
