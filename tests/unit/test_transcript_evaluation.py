import json
from copy import deepcopy

import pytest

from app.cli.evaluate_transcript import main
from app.domain.transcript_evaluation import (
    compare_runs,
    edit_distance,
    evaluate,
    fingerprint,
    normalize_text,
    reference_template,
)


def report():
    return {
        "analysis_id": "fixture-analysis",
        "transcript_version": "fixture-asr",
        "policy_version": "fixture-review",
        "segments": [
            {
                "id": sid,
                "start_ms": index * 2000,
                "end_ms": (index + 1) * 2000,
                "text": text,
                "quality": {},
                "priority": priority,
                "recognition_reasons": reasons,
                "display_reasons": display,
            }
            for index, (sid, text, priority, reasons, display) in enumerate(
                [
                    ("s0", "안녕 하세요!", "medium", [], ["TEXT_LIMIT"]),
                    ("s1", "사과", "high", ["LOW_CONFIDENCE"], []),
                    ("s2", "포도", "none", [], ["WORD_TIMESTAMPS_UNAVAILABLE"]),
                ]
            )
        ],
    }


def test_no_ground_truth_does_not_invent_quality_metrics():
    source = report()
    before = deepcopy(source)
    result = evaluate(source)
    assert source == before
    assert result["review_queue_flagged"] == 2 and result["recognition_flagged"] == 1
    assert result["display_flagged"] == 1
    assert result["cer"] is None and result["quality_pass"] is None
    assert result["recognition_detector"]["recall"] is None
    assert result["reference_segments"] == 0 and result["external_calls"] == 0


def test_identical_run_is_agreement_and_never_accuracy():
    source = report()
    comparison = compare_runs(source, source)
    assert comparison["comparison_kind"] == "run_agreement_not_accuracy"
    assert comparison["shared_segments"] == 3 and comparison["text_changed_ids"] == []
    changed = deepcopy(source)
    changed["segments"][0]["text"] = "changed"
    changed["segments"][1]["end_ms"] += 1
    comparison = compare_runs(source, changed)
    assert comparison["text_changed_ids"] == ["s0"]
    assert comparison["time_changed_ids"] == ["s1"]


def test_partial_verified_reference_and_separate_detectors():
    source = report()
    refs = reference_template(source)
    refs["references"][0].update(human_verified=True, decision="ok", reference_text="안녕하세요")
    refs["references"][1].update(human_verified=True, decision="error", reference_text="사자")
    result = evaluate(source, refs)
    assert result["character_edits"] == 1 and result["reference_characters"] == 7
    assert result["cer"] == 1 / 7 and result["cer_scope"] == "verified_subset"
    assert result["recognition_detector"]["precision_on_reviewed"] == 1
    assert result["review_queue"]["precision_on_reviewed"] == 0.5
    assert result["recognition_detector"]["recall"] is None


def test_full_labels_can_measure_missed_recognition_errors():
    source = report()
    refs = reference_template(source)
    for row, decision in zip(refs["references"], ("ok", "error", "error"), strict=True):
        row.update(human_verified=True, decision=decision)
    result = evaluate(source, refs)
    assert result["recognition_detector"]["false_negative"] == 1
    assert result["recognition_detector"]["recall"] == 0.5
    assert result["cer"] is None  # Human labels alone are not reference transcriptions.


def test_unverified_text_and_uncertain_labels_are_not_ground_truth():
    source = report()
    refs = reference_template(source)
    refs["references"][0].update(decision="error", reference_text="임의 텍스트")
    refs["references"][1].update(human_verified=True, decision="uncertain")
    result = evaluate(source, refs)
    assert result["reference_segments"] == 0 and result["human_labeled_segments"] == 0


@pytest.mark.parametrize(
    "change",
    [
        lambda refs: refs.update(report_sha256="stale"),
        lambda refs: refs.update(analysis_id="another"),
        lambda refs: refs["references"].append(deepcopy(refs["references"][0])),
        lambda refs: refs["references"][0].update(segment_id="missing"),
        lambda refs: refs["references"][0].update(human_verified="true"),
    ],
)
def test_stale_or_invalid_references_are_rejected(change):
    source = report()
    refs = reference_template(source)
    change(refs)
    with pytest.raises(ValueError):
        evaluate(source, refs)


def test_fingerprint_binds_text_and_times_but_not_current_decisions():
    source = report()
    before = fingerprint(source)
    source["segments"][0]["decision"] = "ok"
    assert fingerprint(source) == before
    source["segments"][0]["end_ms"] += 1
    assert fingerprint(source) != before


def test_zero_denominators_and_empty_reference_do_not_report_perfect_accuracy():
    source = report()
    refs = reference_template(source)
    refs["references"][0].update(human_verified=True, decision="error", reference_text="")
    result = evaluate(source, refs)
    assert result["cer"] is None and result["character_edits"] > 0
    assert result["recognition_detector"]["precision_on_reviewed"] is None
    assert edit_distance("사과", "사자") == 1
    assert normalize_text("Ａ 안녕, Hello!") == "ａ안녕hello"


def test_cli_writes_private_pack_without_overwriting_or_embedding_html(tmp_path):
    source = report()
    source["segments"][0]["text"] = "</script><script>alert(1)</script>"
    path = tmp_path / "input.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    audio = tmp_path / "original.mp3"
    audio.write_bytes(b"audio-fixture")
    args = ["--report", str(path), "--audio", str(audio), "--output", str(tmp_path / "pack")]
    main(args)
    page = (tmp_path / "pack" / "review.html").read_text(encoding="utf-8")
    assert "</script><script>alert(1)</script>" not in page
    assert (tmp_path / "pack" / "audio.mp3").read_bytes() == audio.read_bytes()
    result = json.loads((tmp_path / "pack" / "evaluation.json").read_text())
    assert result["cer"] is None
    with pytest.raises(FileExistsError):
        main(args)
