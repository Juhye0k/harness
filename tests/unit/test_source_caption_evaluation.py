import copy
import hashlib

import pytest

from app.domain.source_caption_evaluation import (
    compare,
    evaluate,
    fixed_screen_reference,
    frame_agreement,
    policy_violations,
    references,
)
from scripts.evaluate_source_captions import render, verified_track
from scripts.ocr_tesseract import parse_words, verified_crop


def observation(text="자막을 확인합니다", count=20):
    return {
        "schema_version": "source-caption-ocr-v1",
        "source_sha256": "a" * 64,
        "sample_step_ms": 100,
        "frames": [{"time_ms": i * 100, "text": text, "confidence": 95} for i in range(count)],
    }


def editor():
    return {
        "source_sha256": "a" * 64,
        "analysis_id": "analysis",
        "candidate_id": "candidate",
        "start_ms": 0,
        "end_ms": 2000,
        "latest_revision": {
            "revision_id": "revision",
            "reviewed": False,
            "cues": [
                {"start_ms": 0, "end_ms": 1000, "lines": ["틀린 자막"]},
            ],
        },
    }


def test_missing_source_fingerprint_cannot_compare_unrelated_video():
    rows = observation()
    rows["source_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        compare(rows, editor())
    rows.pop("source_sha256")
    with pytest.raises(ValueError, match="fingerprint"):
        compare(rows, editor())


def test_missing_frames_rejected_rather_than_extending_reference_over_gap():
    rows = observation()
    del rows["frames"][3]
    with pytest.raises(ValueError, match="missing frame"):
        references(rows, 0, 2000, 0)


def test_empty_reference_is_unscored_not_zero_error_or_a_pass():
    ref = references(observation(""), 0, 2000, 0)
    result = evaluate(ref, editor()["latest_revision"]["cues"])
    assert result["screen_reference_cer"] is None
    assert result["quality_pass"] is None
    assert result["human_audio_cer"] is None
    assert ref["reference_coverage_ratio"] == 0
    assert ref["blocked"][0]["reason"] == "NO_REFERENCE"


def test_low_confidence_or_one_frame_never_becomes_reference():
    rows = observation()
    for row in rows["frames"]:
        row["confidence"] = 20
    assert references(rows, 0, 2000, 0)["cues"] == []
    assert references(observation(count=2), 0, 200, 0)["cues"] == []


def test_held_out_text_never_selects_the_reconstructed_draft():
    rows = observation(count=12)
    for index in range(1, 12, 2):
        rows["frames"][index]["text"] = "완전히 다른 문구"
    trained = references(rows, 0, 1200, 0)
    assert trained["cues"][0]["text"] == "자막을 확인합니다"
    assert frame_agreement(rows, trained["cues"], 0, 1200)["agreement_ratio"] == 0


def test_no_original_editor_mutation_and_no_human_or_production_approval():
    rows, saved = observation(), editor()
    before = copy.deepcopy((rows, saved))
    result = compare(rows, saved)
    assert (rows, saved) == before
    assert result["human_review_changed"] is False
    assert result["screen_draft"]["production_ready"] is False
    assert result["external_calls"] == 0


def test_valid_screen_content_can_still_violate_product_duration_and_density():
    assert policy_violations([]) == {"empty_captions": 1}
    assert policy_violations(
        [
            {
                "start_ms": 0,
                "end_ms": 21000,
                "text": "원본 자막도 그대로 복사하면 긴 자막이 됩니다",
            }
        ]
    ) == {"duration": 1, "eojeol": 1, "line_length": 1}


def test_literal_quotes_in_tesseract_tsv_do_not_swallow_later_rows():
    raw = 'conf\ttext\n90\t"인용문\n93\t다음\n'
    assert parse_words(raw) == [
        {"text": '"인용문', "confidence": 90},
        {"text": "다음", "confidence": 93},
    ]


def test_nonfinite_confidence_is_rejected():
    rows = observation()
    rows["frames"][0]["confidence"] = float("nan")
    with pytest.raises(ValueError, match="confidence"):
        references(rows, 0, 2000, 0)


def test_visual_reference_cannot_be_rebound_to_a_different_frame():
    rows = observation()
    rows["frames"][0]["frame_sha256"] = "b" * 64
    fixed = {
        "source_sha256": "a" * 64,
        "reference_kind": "agent_visual_screen_labels",
        "human_verified": False,
        "cues": [
            {
                "start_ms": 0,
                "end_ms": 1000,
                "text": "원본 자막",
                "evidence_time_ms": 0,
                "evidence_frame_sha256": "c" * 64,
            }
        ],
    }
    with pytest.raises(ValueError, match="source frame"):
        fixed_screen_reference(fixed, rows, 0, 2000)
    rows["frames"][0]["frame_sha256"] = None
    fixed["cues"][0]["evidence_frame_sha256"] = None
    with pytest.raises(ValueError, match="source frame"):
        fixed_screen_reference(fixed, rows, 0, 2000)


def test_untrusted_screen_text_is_not_executable_in_report():
    result = compare(observation(), editor())
    result["reference_cues"] = [
        {
            "start_ms": 0,
            "end_ms": 1000,
            "text": '<script>alert("x")</script>',
            "samples": '<img src=x onerror="alert(1)">',
        }
    ]
    page = render(result)
    assert '<script>alert("x")</script>' not in page
    assert "&lt;script&gt;" in page
    assert "<img src=x" not in page
    assert 'data-seek="' not in page


def test_odd_fold_tail_is_bounded_by_observation_horizon():
    ref = references(observation(), 0, 2000, 1)
    assert ref["cues"][0]["end_ms"] == 2000


def test_moving_earlier_text_into_later_interval_cannot_hide_timing_error():
    ref = {
        "cues": [
            {"start_ms": 0, "end_ms": 1000, "text": "첫"},
            {"start_ms": 1000, "end_ms": 2000, "text": "끝"},
        ]
    }
    moved = [{"start_ms": 1100, "end_ms": 1900, "text": "첫 끝"}]
    score = evaluate(ref, moved)
    assert score["screen_reference_cer"] == 0
    assert score["interval_screen_reference_cer"] == 1
    assert score["reference_intervals_without_midpoint_caption"] == 1


def test_wrong_caption_track_and_wrong_crop_rejected(tmp_path):
    raw = b'{"events": []}'
    saved = {"source_sha256": "a" * 64, "source_video_id": "video-A"}
    provenance = {
        **saved,
        "acquired_video_id": "video-A",
        "caption_sha256": hashlib.sha256(raw).hexdigest(),
        "duration_ms": 2000,
    }
    assert verified_track(raw, provenance, saved, 2000) == {"events": []}
    with pytest.raises(ValueError, match="provenance"):
        verified_track(raw + b" ", provenance, saved, 2000)
    provenance["acquired_video_id"] = "video-B"
    with pytest.raises(ValueError, match="provenance"):
        verified_track(raw, provenance, saved, 2000)
    crop = tmp_path / "crop.png"
    crop.write_bytes(b"first crop")
    row = {"crop_name": crop.name, "crop_sha256": hashlib.sha256(crop.read_bytes()).hexdigest()}
    assert verified_crop(tmp_path, row) == crop
    crop.write_bytes(b"different frame")
    with pytest.raises(ValueError, match="Crop bytes"):
        verified_crop(tmp_path, row)
