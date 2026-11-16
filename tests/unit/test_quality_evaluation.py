import json
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from scripts import evaluate_recommendations as evaluation
from scripts.evaluate_recommendations import Interval, Rating, Review, iou, save_new, summarize


def inputs():
    snapshot = {
        "analysis_id": "a",
        "status": "succeeded",
        "config": {"model": "fixture"},
        "candidates": [{"id": "c", "start_ms": 0, "end_ms": 30000}],
    }
    review = Review(analysis_id="a", split="development", ratings=[Rating(candidate_id="c")])
    return snapshot, review


def test_unrated_is_not_zero_or_complete():
    snapshot, review = inputs()
    result = summarize(snapshot, review)
    assert result["usable_fraction"] is None and result["cost"] is None
    assert result["evaluation_status"] == "incomplete" and result["rated_count"] == 0


def test_human_ratings_and_reference_overlap():
    snapshot, review = inputs()
    review.reviewer = "tester"
    review.ratings = [Rating(candidate_id="c", usable=False, boundaries=2, independence=3)]
    review.references = [Interval(start_ms=15000, end_ms=45000)]
    result = summarize(snapshot, review)
    assert result["evaluation_status"] == "complete"
    assert result["usable_fraction"] == 0 and result["mean_boundaries"] == 2
    assert result["mean_best_reference_iou"] == pytest.approx(1 / 3)


def test_mismatched_duplicate_and_missing_rows_rejected():
    snapshot, review = inputs()
    for ratings in [[], [Rating(candidate_id="other")], review.ratings * 2]:
        review.ratings = ratings
        with pytest.raises(ValueError):
            summarize(snapshot, review)
    snapshot, review = inputs()
    review.analysis_id = "different"
    with pytest.raises(ValueError):
        summarize(snapshot, review)


def test_empty_candidates_not_perfect_score():
    snapshot, review = inputs()
    snapshot["candidates"] = []
    review.ratings = []
    result = summarize(snapshot, review)
    assert result["usable_fraction"] is None and result["evaluation_status"] == "incomplete"


def test_score_bounds_and_intervals():
    with pytest.raises(ValidationError):
        Rating(candidate_id="c", boundaries=5)
    with pytest.raises(ValidationError):
        Rating(candidate_id="c", usable="yes")
    with pytest.raises(ValidationError):
        Interval(start_ms=20, end_ms=10)
    assert iou(Interval(start_ms=0, end_ms=10), Interval(start_ms=20, end_ms=30)) == 0


def test_original_evaluation_not_overwritten(tmp_path):
    path = tmp_path / "report.json"
    save_new(path, {"original": True})
    with pytest.raises(FileExistsError):
        save_new(path, {"original": False})
    assert "true" in path.read_text()


def test_capture_only_reads_and_creates_unrated_review(tmp_path, monkeypatch):
    analysis_id = str(uuid4())
    snapshot, _ = inputs()
    snapshot["analysis_id"] = analysis_id
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(200, json=snapshot)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(evaluation.httpx, "Client", lambda **kw: client)
    directory = tmp_path / "evaluation"
    monkeypatch.setattr(
        "sys.argv",
        ["evaluation", "capture", analysis_id, "--split", "holdout", "--output", str(directory)],
    )
    evaluation.main()
    review = Review.model_validate_json((directory / "review.json").read_text(encoding="utf-8"))
    assert review.split == "holdout" and review.ratings[0].usable is None
    assert methods == ["GET"]
    assert json.loads((directory / "snapshot.json").read_text(encoding="utf-8")) == snapshot
