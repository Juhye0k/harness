import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ProviderCall
from tests.integration.test_analysis_flow import BASE, submit

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture worker required"),
]


def test_review_persistence_concurrency_audio_and_browser():
    with httpx.Client(base_url=BASE, timeout=20) as client:
        analysis = submit(client, url="https://fixture.example/analysis.mp4", mode="transcription")
        assert analysis["status"] == "succeeded"
        aid = analysis["analysis_id"]
        url = f"/analyses/{aid}/transcript-review"
        transcript = client.get(f"/analyses/{aid}/transcript").json()
        data = client.get(url).json()
        row = data["segments"][0]
        body = {
            "transcript_version": data["transcript_version"],
            "policy_version": data["policy_version"],
            "revision": 0,
            "decision": "error",
            "note": "<script>not executable</script>",
        }
        target = url + "/" + row["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: client.put(target, json=body).status_code, range(2)))
        assert sorted(statuses) == [200, 409]
        saved = next(r for r in client.get(url).json()["segments"] if r["id"] == row["id"])
        assert saved["revision"] == 1 and saved["note"] == body["note"]
        audio = client.get(f"/analyses/{aid}/review-audio", headers={"Range": "bytes=0-31"})
        assert audio.status_code == 206 and len(audio.content) == 32
        assert client.get(f"/analyses/{aid}/transcript").json() == transcript
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(BASE + f"/recommendations?analysis={aid}")
            panel = page.locator("#review-panel")
            panel.get_by_label("검수 구간 필터").select_option("all")
            card = panel.locator(f'[data-segment-id="{row["id"]}"]')
            expect(card.get_by_role("status")).to_have_text("저장된 판정: error")
            card.get_by_role("button", name="앞뒤 2초 듣기").click()
            page.wait_for_function("document.querySelector('#review-panel audio').currentTime > 0")
            card.get_by_label(f"{row['id']} 검수 메모").fill("검수 완료")
            card.get_by_role("button", name="이상 없음", exact=True).click()
            expect(panel.get_by_text("저장된 판정: ok", exact=True)).to_be_visible()
            page.reload()
            panel.get_by_label("검수 구간 필터").select_option("all")
            expect(panel.get_by_text("저장된 판정: ok", exact=True)).to_be_visible()
            with page.expect_download() as download:
                panel.get_by_role("button", name="검수 보고서 JSON 다운로드").click()
            assert download.value.suggested_filename.endswith(".json")
            card = panel.locator(f'[data-segment-id="{row["id"]}"]')
            note = card.get_by_label(f"{row['id']} 검수 메모")
            note.fill("저장 실패 시 보존")
            page.route(
                "**/transcript-review/*",
                lambda route: route.fulfill(status=409, content_type="application/json", body="{}"),
            )
            card.get_by_role("button", name="판단 어려움", exact=True).click()
            expect(card.get_by_role("status")).to_contain_text("저장 충돌")
            expect(note).to_have_value("저장 실패 시 보존")
            page.unroute("**/transcript-review/*")
            page.route(
                "**/transcript-review",
                lambda route: route.fulfill(status=500, content_type="application/json", body="{}"),
            )
            page.reload()
            expect(panel.get_by_role("status")).to_contain_text("전사 완료 상태와 별개")
            browser.close()
        with Session(get_engine()) as session:
            calls = list(
                session.scalars(select(ProviderCall).where(ProviderCall.analysis_id == UUID(aid)))
            )
            assert len(calls) == 1 and calls[0].stage == "transcription"
