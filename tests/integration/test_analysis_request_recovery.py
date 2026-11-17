"""Response loss and receipt isolation with real database/worker/browser."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from playwright.sync_api import expect
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.analysis_requests import create_once
from app.models import AnalysisJob, AnalysisRequestReceipt, Asset, ProviderCall, utcnow
from app.services.access import current_user
from tests.integration.failure_artifacts import observed_browser
from tests.integration.test_analysis_flow import BASE, wait
from tests.integration.test_auth_data import setup as auth_setup  # noqa: F401

pytestmark = [pytest.mark.integration]


@pytest.mark.skipif(os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture workers required")
def test_concurrent_receipt_creates_one_analysis_and_one_provider_call_per_stage():
    rid = uuid4()
    body = {"request_id": str(rid), "url": "https://fixture.example/analysis.mp4"}

    def submit(_):
        with httpx.Client(base_url=BASE, timeout=30) as client:
            response = client.post("/analyses", json=body)
            assert response.status_code == 202, response.text
            return response.json()["analysis_id"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(submit, range(4)))
    assert len(set(ids)) == 1
    with httpx.Client(base_url=BASE, timeout=20) as client:
        result = wait(client, f"/analyses/{ids[0]}")
        assert result["status"] == "succeeded"
        assert client.post("/analyses", json={**body, "purpose": "humor"}).status_code == 409
        assert client.get(f"/analysis-requests/{rid}").json()["analysis_id"] == ids[0]
    with Session(AnalysisRepository().engine) as session:
        receipt = session.get(AnalysisRequestReceipt, ("local-development", rid))
        assert len(receipt.payload_hash) == 64 and receipt.analysis_id == UUID(ids[0])
        counts = session.execute(
            select(ProviderCall.stage, func.count())
            .where(ProviderCall.analysis_id == UUID(ids[0]))
            .group_by(ProviderCall.stage)
        ).all()
        assert dict(counts) == {"transcription": 1, "proposal": 1, "scoring": 1}


@pytest.mark.skipif(os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture workers required")
def test_browser_restores_analysis_after_server_accepted_but_response_was_lost():
    with observed_browser("test_analysis_request_recovery") as page:
        posts = []
        accepted = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)

        def lose_response(route):
            response = route.fetch()
            assert response.status == 202
            accepted.append(response.json()["analysis_id"])
            route.abort()

        page.route("**/analyses", lose_response)
        page.goto(BASE + "/recommendations")
        page.locator("#mode").select_option("recommendation")
        page.locator("#url").fill("https://fixture.example/analysis.mp4")
        page.locator("#analyze").click()
        expect(page.locator("#recover-analysis")).to_be_visible()
        expect(page.locator("#recover-analysis")).to_be_enabled()
        expect(page.locator("#analyze")).to_be_disabled()
        assert len(accepted) == 1
        page.reload()
        expect(page).to_have_url(BASE + "/recommendations?analysis=" + accepted[0])
        expect(page.locator(".edit-candidate")).to_have_count(2, timeout=90000)
        assert len([url for url in posts if url.endswith("/analyses")]) == 1


@pytest.mark.skipif(not os.getenv("AUTH_TEST_DATABASE_URL"), reason="Dedicated auth DB required")
def test_receipt_owner_expiry_and_deleted_parent_tombstone(auth_setup):  # noqa: F811
    client, engine, user, other, _, _ = auth_setup
    rid = uuid4()
    repo = AnalysisRepository(engine)
    token = current_user.set(user)
    try:
        job, created = create_once(
            repo,
            rid,
            "a" * 64,
            "https://fixture.example/private.mp4",
            None,
            "unknown",
            "balanced",
            lambda: {"asr_version": "fixture"},
        )
        assert created
    finally:
        current_user.reset(token)
    assert client.get(f"/analysis-requests/{rid}").json()["analysis_id"] == str(job.id)
    # Another user's receipt is not visible even with a known request ID.
    other_id = uuid4()
    with Session(engine) as s, s.begin():
        s.add(
            AnalysisRequestReceipt(
                owner_key=str(other),
                request_id=other_id,
                payload_hash="b" * 64,
                analysis_id=job.id,
                expires_at=utcnow() + timedelta(days=7),
            )
        )
    assert client.get(f"/analysis-requests/{other_id}").status_code == 404
    with Session(engine) as s, s.begin():
        s.get(AnalysisRequestReceipt, (str(user), rid)).expires_at = utcnow() - timedelta(seconds=1)
    assert client.get(f"/analysis-requests/{rid}").status_code == 410
    with Session(engine) as s, s.begin():
        receipt = s.get(AnalysisRequestReceipt, (str(user), rid))
        receipt.expires_at = utcnow() + timedelta(days=7)
        s.get(Asset, job.asset_id).deleted_at = utcnow()
    assert client.get(f"/analysis-requests/{rid}").status_code == 410
    with Session(engine) as s, s.begin():
        s.delete(s.get(AnalysisJob, job.id))
    with Session(engine) as s:
        assert s.get(AnalysisRequestReceipt, (str(user), rid)).analysis_id is None
    assert client.get(f"/analysis-requests/{rid}").status_code == 410
