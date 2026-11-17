import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from scripts.evaluate_recommendations import Rating, Review, fingerprint, save_new
from scripts.review_recommendations import create_app


def prepared(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr("app.adapters.media.probe", lambda _: SimpleNamespace(duration=90))
    monkeypatch.setattr("app.services.video.checksum", lambda _: "source")
    transcript = {"segments": [{"id": "s0", "start_ms": 0, "end_ms": 1000, "text": "fixture"}]}
    snapshot = {
        "analysis_id": "a",
        "status": "succeeded",
        "config": {},
        "candidates": [{"id": "c", "start_ms": 0, "end_ms": 30000}],
        "evaluation_input": {
            "source_sha256": "source",
            "duration_ms": 90000,
            "transcript_sha256": fingerprint(transcript["segments"]),
        },
    }
    review = Review(
        analysis_id="a",
        split="development",
        snapshot_sha256=fingerprint(snapshot),
        ratings=[Rating(candidate_id="c")],
    )
    directory = tmp_path / "pack"
    for name, value in [
        ("snapshot.json", snapshot),
        ("review.json", review.model_dump()),
        ("transcript.json", transcript),
    ]:
        save_new(directory / name, value)
    return directory, source


def test_save_restore_conflict_and_automation_handoff(tmp_path, monkeypatch):
    directory, source = prepared(tmp_path, monkeypatch)
    with TestClient(create_app(directory, source)) as client:
        data = client.get("/api/review").json()
        review = data["review"]
        review["reviewer"] = "fixture-human"
        review["ratings"][0].update(
            selected=False,
            usable=False,
            boundaries=1,
            independence=1,
            reasons=["context"],
            notes="missing context",
        )
        saved = client.post("/api/review", json={"revision": None, "review": review})
        assert saved.status_code == 200
        assert saved.json()["handoff"]["status"] == "ready_for_analysis"
        assert saved.json()["report"]["selected_ids"] == []
        assert list(directory.glob("web-reviews/*/loop/session.json"))
        assert client.get("/api/review").json()["review"] == review
        assert (
            client.post("/api/review", json={"revision": None, "review": review}).status_code == 409
        )
        assert client.get("/api/download/handoff").status_code == 200
        assert (
            client.post(
                "/api/review",
                headers={"Origin": "https://evil.example"},
                json={"revision": None, "review": review},
            ).status_code
            == 403
        )


def test_invalid_reference_and_policy_are_not_saved(tmp_path, monkeypatch):
    directory, source = prepared(tmp_path, monkeypatch)
    with TestClient(create_app(directory, source)) as client:
        review = client.get("/api/review").json()["review"]
        review["references"] = [{"start_ms": 0, "end_ms": 90001}]
        assert client.post("/api/review", json={"review": review}).status_code == 422
        review["references"] = []
        review["policy_version"] = "weaker"
        assert client.post("/api/review", json={"review": review}).status_code == 422
        assert not list(directory.glob("web-reviews/*/review.json"))


def test_frozen_transcript_change_rejected(tmp_path, monkeypatch):
    directory, source = prepared(tmp_path, monkeypatch)
    (directory / "transcript.json").write_text(json.dumps({"segments": []}))
    with pytest.raises(ValueError, match="전사"):
        create_app(directory, source)
