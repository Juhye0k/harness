from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import analyses
from app.domain.recommendations import normalize
from app.domain.subtitles import POLICY, VERSION, build_subtitles, compact, srt, validate_words
from app.domain.video import VideoError
from app.main import app


def segment(text="한국어 문장. 다음 이야기!", parts=None):
    parts = parts or ["한국어", "문장.", "다음", "이야기!"]
    return {
        "id": "s0000",
        "start_ms": 1000,
        "end_ms": 9000,
        "text": text,
        "words": [
            {"text": word, "start_ms": 1000 + i * 1900, "end_ms": 2500 + i * 1900}
            for i, word in enumerate(parts)
        ],
    }


def test_sentence_boundaries_preserve_source_and_exact_word_times():
    source = segment()
    before = deepcopy(source)
    result = build_subtitles([source])
    assert result["version"] == VERSION and result["policy_status"] == "product_draft"
    assert result["time_origin"] == "source_video"
    assert [(c["text"], c["start_ms"], c["end_ms"]) for c in result["cues"]] == [
        ("한국어 문장.", 1000, 4400),
        ("다음 이야기!", 4800, 8200),
    ]
    assert source == before
    assert srt(result).startswith("1\n00:00:01,000 --> 00:00:04,400\n한국어 문장.\n\n")


def test_twenty_one_second_173_character_segment_is_split_without_loss():
    text = " ".join(["한국어문장"] * 29)
    assert len(text) == 173
    source = {
        "id": "s0000",
        "start_ms": 0,
        "end_ms": 21000,
        "text": text,
        "words": [
            {"text": word, "start_ms": i * 724, "end_ms": (i + 1) * 724}
            for i, word in enumerate(text.split())
        ],
    }
    result = build_subtitles([source])
    assert len(result["cues"]) > 1 and not result["review_required"]
    assert " ".join(c["text"] for c in result["cues"]) == text
    for cue in result["cues"]:
        assert cue["end_ms"] - cue["start_ms"] <= POLICY.max_duration_ms
        assert len(cue["lines"]) <= POLICY.max_lines
        assert all(len(line) <= POLICY.max_line_chars for line in cue["lines"])


@pytest.mark.parametrize(
    "parts,text",
    [
        (["안녕", "하세요.", "“반가워요!”"], "안녕하세요.  “반가워요!”"),
        (["하나", ",둘", "…", "셋？"], "하나,둘… 셋？"),
        (["같은", "말", "같은", "말"], "같은 말 같은 말"),
    ],
)
def test_korean_spacing_punctuation_and_legitimate_repetition(parts, text):
    source = segment(text, parts)
    source["end_ms"] = 20000
    result = build_subtitles([source])
    assert compact("".join(c["text"] for c in result["cues"])) == compact(text)
    assert compact("".join("".join(c["lines"]) for c in result["cues"])) == compact(text)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["words"].pop(),
        lambda s: s["words"].append(s["words"][-1]),
        lambda s: s["words"].reverse(),
        lambda s: s["words"][0].update(text="틀린말"),
        lambda s: s["words"][0].update(start_ms=999),
        lambda s: s["words"][0].update(end_ms=1000),
        lambda s: s["words"][0].update(start_ms=True),
        lambda s: s["words"][0].update(end_ms=float("nan")),
        lambda s: s["words"][1].update(start_ms=2400),
        lambda s: s["words"][-1].update(end_ms=9001),
        lambda s: s.update(words=[]),
        lambda s: s.update(words=None),
    ],
)
def test_inconsistent_word_coverage_or_times_fail_closed(change):
    source = segment()
    change(source)
    with pytest.raises(VideoError) as exc:
        validate_words(source)
    assert exc.value.code == "MODEL_RESPONSE_INVALID"


def test_normalization_preserves_words_and_rejects_cross_segment_overlap():
    source = segment()
    raw = {
        "phrases": [
            {
                "offsetMilliseconds": source["start_ms"],
                "durationMilliseconds": source["end_ms"] - source["start_ms"],
                "text": source["text"],
                "words": source["words"],
            }
        ]
    }
    raw["_normalized_word_timestamps"] = True
    assert normalize(raw, 9000) == [source]
    raw["phrases"].append(deepcopy(raw["phrases"][0]))
    with pytest.raises(VideoError):
        normalize(raw, 9000)


def test_legacy_segments_keep_times_and_report_constraints_without_guessing():
    source = segment()
    del source["words"]
    source.update(text=" ".join(["오래말하는문장"] * 20), end_ms=22000)
    result = build_subtitles([source])
    assert len(result["cues"]) == 1
    cue = result["cues"][0]
    assert (cue["start_ms"], cue["end_ms"]) == (1000, 22000)
    assert cue["text"] == source["text"] and cue["timing"] == "segment"
    assert {"WORD_TIMESTAMPS_UNAVAILABLE", "TEXT_LIMIT", "DURATION_LIMIT"} <= set(cue["warnings"])
    assert cue["review_required"]


def test_unbreakable_word_and_fast_speech_remain_visible_for_review():
    source = segment("가" * 45, ["가" * 45])
    source["words"][0]["end_ms"] = 1200
    result = build_subtitles([source])
    cue = result["cues"][0]
    assert cue["text"] == "가" * 45 and len(result["cues"]) == 1
    assert set(cue["warnings"]) == {"TEXT_LIMIT", "SHORT_DURATION", "READING_SPEED"}


def test_long_word_duration_pause_and_overlapping_legacy_cues_are_explicit():
    source = segment("긴말", ["긴말"])
    source["words"][0]["end_ms"] = 9000
    assert "DURATION_LIMIT" in build_subtitles([source])["cues"][0]["warnings"]
    source = segment("하나 둘", ["하나", "둘"])
    source["words"][1].update(start_ms=4000, end_ms=5000)
    assert len(build_subtitles([source])["cues"]) == 2
    del source["words"]
    result = build_subtitles([source, source])
    assert "OVERLAPPING_CUES" in result["cues"][1]["warnings"]


def test_no_speech_and_srt_time_format():
    assert build_subtitles([])["cues"] == [] and srt(build_subtitles([])) == ""
    source = {"id": "s0", "text": "내용", "start_ms": 3661002, "end_ms": 3662999}
    assert "01:01:01,002 --> 01:01:02,999" in srt(build_subtitles([source]))


@pytest.mark.parametrize("state", ["queued", "running", "failed"])
@pytest.mark.parametrize("suffix", ["subtitles", "subtitles.srt"])
def test_subtitle_endpoints_never_create_or_read_incomplete_transcript(state, suffix):
    repo = SimpleNamespace(get=lambda _: SimpleNamespace(status=state, stage="transcription"))
    app.dependency_overrides[analyses.repository] = lambda: repo
    try:
        with TestClient(app) as client:
            assert client.get(f"/analyses/{uuid4()}/{suffix}").status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_json_and_download_are_same_readonly_projection():
    identifier = uuid4()
    source = [segment()]
    before = deepcopy(source)
    job = SimpleNamespace(
        id=identifier,
        asset_id=uuid4(),
        status="succeeded",
        config={"asr_version": "legacy-readable-version"},
    )
    repo = SimpleNamespace(get=lambda _: job, read_transcript=lambda *args: source)
    app.dependency_overrides[analyses.repository] = lambda: repo
    try:
        with TestClient(app) as client:
            raw = client.get(f"/analyses/{identifier}/transcript").json()
            result = client.get(f"/analyses/{identifier}/subtitles").json()
            download = client.get(f"/analyses/{identifier}/subtitles.srt")
        assert raw["segments"] == before == source
        assert result["transcript_version"] == "legacy-readable-version"
        assert download.text == srt(result)
        assert "attachment; filename=" in download.headers["content-disposition"]
        assert download.headers["content-type"].startswith("application/x-subrip")
    finally:
        app.dependency_overrides.clear()


def test_azure_native_word_payload_does_not_change_legacy_normalization():
    raw = {
        "phrases": [
            {
                "offsetMilliseconds": 0,
                "durationMilliseconds": 2000,
                "text": "기존 전사",
                "words": [{"offsetMilliseconds": 0, "text": "기존"}],
            }
        ]
    }
    assert normalize(raw, 2000) == [
        {"id": "s0000", "start_ms": 0, "end_ms": 2000, "text": "기존 전사"}
    ]
