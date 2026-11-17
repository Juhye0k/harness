"""Frozen evaluation against real API/DB/worker, using only synthetic providers."""

import json
import os
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.analysis_repository import AnalysisRepository
from app.config import get_settings
from app.db import get_engine
from app.models import ProviderCall
from scripts.evaluate_recommendations import main
from tests.integration.test_analysis_flow import BASE, submit

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture worker required"),
]


def test_capture_review_compare_never_submits_new_provider_calls(tmp_path):
    with httpx.Client(base_url=BASE, timeout=15) as client:
        analysis = submit(client)
    assert analysis["status"] == "succeeded"
    asset = AnalysisRepository().asset(UUID(analysis["asset_id"]))
    source = get_settings().video_data_dir / asset.path

    def calls():
        with Session(get_engine()) as session:
            return session.scalar(
                select(func.count())
                .select_from(ProviderCall)
                .where(ProviderCall.analysis_id == UUID(analysis["analysis_id"]))
            )

    before = calls()
    directory = tmp_path / "evaluation"
    main(
        [
            "capture",
            analysis["analysis_id"],
            "--base-url",
            BASE,
            "--source",
            str(source),
            "--split",
            "development",
            "--output",
            str(directory),
        ]
    )
    path = directory / "review.json"
    review = json.loads(path.read_text(encoding="utf-8"))
    review["reviewer"] = "synthetic-test-only"
    for rating in review["ratings"]:
        rating.update(selected=False, usable=True, boundaries=4, independence=4)
    path.write_text(json.dumps(review), encoding="utf-8")
    main(["report", str(directory)])
    report = directory / "report.json"
    main(["compare", str(report), str(report), "--output", str(tmp_path / "comparison.json")])
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["usable_count"] == len(analysis["candidates"])
    assert result["selected_ids"] == []
    assert calls() == before
