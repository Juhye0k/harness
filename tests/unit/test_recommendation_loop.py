import copy

import pytest

from app.domain.recommendation_loop import compare_reports, decide
from scripts.evaluate_recommendations import Rating, Review, fingerprint, summarize
from scripts.recommendation_loop import Policy


def frozen():
    snapshot = {
        "analysis_id": "a",
        "status": "succeeded",
        "config": {"model": "fixture"},
        "evaluation_input": {
            "source_sha256": "source",
            "transcript_sha256": "text",
            "duration_ms": 90000,
            "asr_version": "v1",
        },
        "candidates": [{"id": "c", "start_ms": 0, "end_ms": 30000}],
    }
    review = Review(
        analysis_id="a",
        split="development",
        reviewer="human",
        snapshot_sha256=fingerprint(snapshot),
        ratings=[
            Rating(candidate_id="c", selected=False, usable=True, boundaries=4, independence=4)
        ],
    )
    return snapshot, review


def test_selection_is_not_quality_and_unknown_stays_unknown():
    snapshot, review = frozen()
    result = summarize(snapshot, review)
    assert result["usable_count"] == 1 and result["selected_ids"] == []
    review.ratings[0].usable = None
    review.ratings[0].uncertain = True
    result = summarize(snapshot, review)
    assert result["uncertain_count"] == 1 and result["unreviewed_count"] == 0
    assert result["usable_fraction"] is None


def test_binding_and_edit_validation():
    snapshot, review = frozen()
    review.ratings[0].usable = False
    with pytest.raises(ValueError, match="이유"):
        summarize(snapshot, review)
    review.ratings[0].reasons = ["context"]
    assert summarize(snapshot, review)["usable_count"] == 0
    from scripts.evaluate_recommendations import Interval

    review.ratings[0].edited_range = Interval(start_ms=0, end_ms=90001)
    with pytest.raises(ValueError, match="범위"):
        summarize(snapshot, review)
    review.ratings[0].edited_range = None
    snapshot["config"]["model"] = "changed"
    with pytest.raises(ValueError, match="해시"):
        summarize(snapshot, review)


def test_comparison_requires_identical_inputs_but_not_candidate_ids():
    snapshot, review = frozen()
    before = summarize(snapshot, review)
    after = copy.deepcopy(before)
    after.update(analysis_id="b", config={"model": "improved"}, usable_count=0)
    after["feedback"][0]["candidate_id"] = "different"
    assert compare_reports(before, after)["metrics"]["usable_count"]["delta"] == -1
    after["evaluation_input"]["transcript_sha256"] = "changed"
    with pytest.raises(ValueError):
        compare_reports(before, after)


def test_convergence_resets_on_failure_change_and_worker():
    policy = {"issues": []}
    passed = {"kind": "check", "source_sha256": "code", "passed": True}
    assert decide(policy, [passed], "code", {})["status"] == "needs_check"
    assert decide(policy, [passed, passed], "code", {})["status"] == "complete"
    for middle in ({**passed, "passed": False}, {"kind": "worker"}):
        assert decide(policy, [passed, middle, passed], "code", {})["status"] != "complete"
    assert decide(policy, [passed, passed], "changed", {})["status"] != "complete"


def test_human_approval_cannot_survive_code_changes_and_minor_does_not_block():
    issue = {"id": "quality", "severity": "major", "verification": "human"}
    policy = {"issues": [issue]}
    passed = {"kind": "check", "source_sha256": "code", "passed": True}
    assert decide(policy, [passed, passed], "code", {})["status"] == "waiting_human"
    assert decide(policy, [passed, passed], "code", {"quality": "code"})["status"] == "complete"
    assert decide(policy, [passed, passed], "new", {"quality": "code"})["status"] == "waiting_human"
    issue["severity"] = "minor"
    assert decide(policy, [passed, passed], "code", {})["minor_issues"] == [issue]


def test_policy_requires_checks_and_unique_issues():
    with pytest.raises(ValueError):
        Policy(checks={"basic": ["python"]}, issues=[])
    issue = {
        "id": "bug",
        "severity": "major",
        "description": "bad output",
        "evidence": "fixture",
        "verification": "regression",
        "check": "missing",
    }
    with pytest.raises(ValueError):
        Policy(checks={"basic": ["python"], "integration": ["python"]}, issues=[issue])


def test_capture_frozen_transcript_is_read_only_and_reportable(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    import httpx

    from scripts import evaluate_recommendations as cli

    snapshot, _ = frozen()
    snapshot.pop("evaluation_input")
    snapshot.update(
        analysis_id=str(uuid4()), asset_id="asset", genre="conversation", purpose="balanced"
    )
    snapshot["config"]["asr_version"] = "asr-v1"
    transcript = {
        "analysis_id": snapshot["analysis_id"],
        "asset_id": "asset",
        "version": "asr-v1",
        "segments": [{"id": "s0", "text": "fixture"}],
    }
    requests = []

    def handler(request):
        requests.append(request.method)
        return httpx.Response(
            200, json=transcript if request.url.path.endswith("transcript") else snapshot
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(cli.httpx, "Client", lambda **kw: client)
    monkeypatch.setattr("app.adapters.media.probe", lambda path: SimpleNamespace(duration=90))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    directory = tmp_path / "round"
    cli.main(
        [
            "capture",
            snapshot["analysis_id"],
            "--source",
            str(source),
            "--split",
            "development",
            "--output",
            str(directory),
        ]
    )
    assert requests == ["GET", "GET"]
    cli.main(["report", str(directory)])
    import json

    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    assert report["evaluation_input"]["transcript_sha256"] == fingerprint(transcript["segments"])
    assert report["usable_fraction"] is None
