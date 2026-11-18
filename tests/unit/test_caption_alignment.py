import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.caption_alignment import align_candidate_captions, editor_suggestion


@pytest.fixture
def sample(tmp_path):
    asset = SimpleNamespace(id=uuid4(), sha256="a" * 64, duration_ms=2500)
    directory = tmp_path / "assets" / str(asset.id)
    directory.mkdir(parents=True)
    words = ["원본", "자막", "단어", "정렬"]
    segments = [
        {
            "id": "s0",
            "text": " ".join(words),
            "start_ms": 0,
            "end_ms": 1950,
            "words": [
                {"text": word, "start_ms": pos * 500, "end_ms": pos * 500 + 450}
                for pos, word in enumerate(words)
            ],
        }
    ]
    candidate = {"start_ms": 0, "end_ms": 2000, "segments": [{"id": "s0"}]}
    observations = {
        "schema_version": "source-caption-ocr-v1",
        "source_sha256": asset.sha256,
        "sample_step_ms": 100,
        "frames": [
            {"time_ms": point, "text": "개울 풍경" if point < 600 else "완료 단계"}
            for point in range(0, 2200, 100)
        ],
    }
    return asset, segments, candidate, observations, directory / "caption-observations.json"


def test_alignment_uses_transition_but_keeps_timed_words_and_revision_unreviewed(tmp_path, sample):
    asset, segments, candidate, observations, path = sample
    path.write_text(json.dumps(observations), encoding="utf-8")
    align_candidate_captions(tmp_path, asset, segments, [candidate])
    display, alignment = editor_suggestion(candidate, segments)
    assert alignment == {
        "status": "aligned",
        "cut_words": 0,
        "version": "persistent-ocr-transcript-v1",
    }
    assert display["review_required"]
    assert [(cue["start_ms"], cue["end_ms"], cue["lines"]) for cue in display["cues"]] == [
        (0, 450, ["원본"]),
        (500, 1950, ["자막 단어 정렬"]),
    ]
    assert segments[0]["text"] == "원본 자막 단어 정렬"


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        ("no_cache", "observations_unavailable"),
        ("partial_cache", "observations_unavailable"),
        ("other_asset", "alignment_needs_review"),
        ("missing_words", "alignment_needs_review"),
        ("no_transition", "alignment_needs_review"),
    ],
)
def test_alignment_falls_back_without_inventing_timing(tmp_path, sample, failure, status):
    asset, segments, candidate, observations, path = sample
    if failure == "other_asset":
        observations["source_sha256"] = "b" * 64
    if failure == "partial_cache":
        observations["frames"] = observations["frames"][10:]
    if failure == "missing_words":
        segments[0].pop("words")
    if failure == "no_transition":
        for frame in observations["frames"]:
            frame["text"] = ""
    if failure != "no_cache":
        path.write_text(json.dumps(observations), encoding="utf-8")
    baseline, _ = editor_suggestion(candidate, segments)
    align_candidate_captions(tmp_path, asset, segments, [candidate])
    display, alignment = editor_suggestion(candidate, segments)
    assert alignment == {"status": status}
    assert display == baseline
    if failure == "missing_words":
        assert not display["cues"]
        assert display["blocked_segments"][0]["reason"] == "WORD_TIMING_UNVERIFIED"
