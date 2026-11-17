from copy import deepcopy

import pytest

from app.adapters.groq import parse_transcription
from app.cli.align_subtitles import compare, main
from app.domain.recommendations import normalize
from app.domain.subtitles import compact
from app.domain.word_alignment import recover


def sample():
    return {
        "segments": [
            {"start": 0, "end": 4, "text": "first sentence."},
            {"start": 4, "end": 12, "text": "second sentence. third sentence."},
        ],
        "words": [
            {"start": 0, "end": 2, "word": "first"},
            {"start": 2, "end": 4.14, "word": "sentence."},
            {"start": 4.2, "end": 6, "word": "second"},
            {"start": 6, "end": 8, "word": "sentence."},
            {"start": 8.2, "end": 10, "word": "third"},
            {"start": 10, "end": 12, "word": "sentence."},
        ],
    }


def primary(raw):
    return [
        {
            "id": f"s{i:04d}",
            "text": s["text"],
            "start_ms": round(s["start"] * 1000),
            "end_ms": round(s["end"] * 1000),
        }
        for i, s in enumerate(raw["segments"])
    ]


def test_one_bad_boundary_does_not_discard_other_segments():
    raw = sample()
    original = deepcopy(raw)
    segments = normalize(parse_transcription(raw), 12000)
    assert raw == original
    assert "words" not in segments[0]
    assert segments[0]["end_ms"] == 4000
    assert len(segments[1]["words"]) == 4
    assert segments[1]["text"] == raw["segments"][1]["text"]


def test_text_mismatch_only_invalidates_affected_segment():
    raw = sample()
    raw["words"][1].update(word="a different sentence.", end=4)
    recovered, report = recover(primary(raw), raw["words"])
    assert report["matched_segments"] == 1 and report["fallback_segments"] == 1
    assert "words" not in recovered[0] and "words" in recovered[1]


def test_time_reversal_in_one_phrase_does_not_poison_unrelated_phrase():
    raw = sample()
    raw["words"][0].update(start=2, end=3)
    raw["words"][1].update(start=0, end=1)
    recovered, report = recover(primary(raw), raw["words"])
    assert report["matched_segments"] == 1
    assert "words" not in recovered[0]
    assert [w["text"] for w in recovered[1]["words"]] == [
        "second",
        "sentence.",
        "third",
        "sentence.",
    ]


def test_explicit_bounded_preview_uses_real_word_times_without_source_mutation():
    raw = sample()
    transcript = {"segments": primary(raw)}
    before = deepcopy(transcript)
    subtitles, report = compare(transcript, raw, 12000, 150)
    assert transcript == before and report["source_preserved"]
    assert report["experimental"] and report["matched_segments"] == 2
    assert report["boundary_deltas"][0]["end_delta_ms"] == 140
    assert subtitles["version"] == "ko-display-bounded-preview-v1"
    assert subtitles["cues"][0]["end_ms"] == 4140
    assert compact("".join(c["text"] for c in subtitles["cues"])) == compact(
        "".join(s["text"] for s in transcript["segments"])
    )


def test_tolerance_limit_and_video_end_are_never_exceeded():
    raw = sample()
    raw["words"][1]["end"] = 4.3
    recovered, report = recover(primary(raw), raw["words"], boundary_tolerance_ms=250)
    assert "words" not in recovered[0] and report["fallback_segments"] == 1
    raw = sample()
    raw["words"][-1]["end"] = 12.1
    recovered, _ = recover(primary(raw), raw["words"], boundary_tolerance_ms=250, duration_ms=12000)
    assert "words" not in recovered[1]


def test_ambiguous_repeated_phrase_is_not_arbitrarily_assigned():
    source = [{"id": "s0", "start_ms": 0, "end_ms": 2000, "text": "same"}]
    words = [{"start": 0, "end": 0.8, "word": "same"}, {"start": 1, "end": 1.8, "word": "same"}]
    recovered, report = recover(source, words, boundary_tolerance_ms=150)
    assert "words" not in recovered[0]
    assert report["segments"][0]["reason"] == "AMBIGUOUS_MATCH"


def test_words_cannot_be_reused_for_overlapping_source_segments():
    source = [
        {"id": "s0", "start_ms": 0, "end_ms": 2000, "text": "same"},
        {"id": "s1", "start_ms": 0, "end_ms": 2000, "text": "same"},
    ]
    recovered, report = recover(source, [{"start": 0, "end": 2, "word": "same"}])
    assert report["matched_segments"] == 1
    assert "words" in recovered[0] and "words" not in recovered[1]


@pytest.mark.parametrize(
    "words",
    [
        None,
        [{"start": True, "end": 2, "word": "x"}],
        [{"start": 0, "end": float("nan"), "word": "x"}],
        [{"start": 2, "end": 3, "word": "x"}, {"start": 0, "end": 1, "word": "y"}],
    ],
)
def test_malformed_words_keep_primary_segments(words):
    source = primary(sample())
    before = deepcopy(source)
    recovered, report = recover(source, words)
    assert source == before
    assert report["matched_segments"] == 0
    assert all("words" not in row for row in recovered)


def test_saved_response_must_match_source_transcript():
    raw = sample()
    source = {"segments": primary(raw)}
    source["segments"][0]["text"] = "different"
    with pytest.raises(ValueError, match="does not belong"):
        compare(source, raw, 12000)


def test_cli_never_overwrites_source_or_output(tmp_path):
    import json

    raw = sample()
    response = tmp_path / "response.json"
    transcript = tmp_path / "transcript.json"
    response.write_text(json.dumps(raw), encoding="utf-8")
    transcript.write_text(json.dumps({"segments": primary(raw)}), encoding="utf-8")
    before = response.read_bytes(), transcript.read_bytes()
    args = [
        "--transcript",
        str(transcript),
        "--response",
        str(response),
        "--duration-ms",
        "12000",
        "--output",
        str(tmp_path / "out"),
    ]
    main(args)
    assert (response.read_bytes(), transcript.read_bytes()) == before
    assert (tmp_path / "out" / "subtitles.srt").is_file()
    with pytest.raises(FileExistsError):
        main(args)
