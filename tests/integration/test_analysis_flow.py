import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.job_publisher import publish_analysis_job
from app.db import get_engine
from app.models import ProviderCall, Transcript

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture worker required"),
]
BASE = os.getenv("TEST_API_URL", "http://api:8000")


def wait(client, path):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] in ("failed", "succeeded"):
            return data
        time.sleep(0.2)
    pytest.fail("Analysis/export timed out")


def submit(client, **kwargs):
    response = client.post(
        "/analyses", json=kwargs or {"url": "https://fixture.example/analysis.mp4"}
    )
    assert response.status_code == 202, response.text
    return wait(client, response.json()["status_url"])


def test_analysis_export_reuse_and_duplicate_delivery():
    with httpx.Client(base_url=BASE, timeout=15) as client:
        analysis = submit(client)
        assert analysis["status"] == "succeeded", analysis
        assert len(analysis["candidates"]) == 2
        assert "source_url" not in str(analysis) and "/data" not in str(analysis)
        cid = analysis["candidates"][0]["id"]
        url = f"/analyses/{analysis['analysis_id']}/candidates/{cid}/exports"
        with ThreadPoolExecutor(max_workers=4) as executor:
            responses = list(executor.map(lambda _: client.post(url), range(4)))
        assert all(r.status_code == 202 for r in responses)
        ids = {r.json()["job_id"] for r in responses}
        assert len(ids) == 1
        job = wait(client, f"/jobs/{ids.pop()}")
        assert job["status"] == "succeeded", job
        assert abs(job["result"]["media"]["duration"] - 30.2) <= 0.1
        assert all(job["result"]["checks"].values())
        assert client.get(job["download_url"]).content[4:8] == b"ftyp"
        assert client.post(url).json()["job_id"] == job["job_id"]
        second = analysis["candidates"][1]
        export = client.post(
            f"/analyses/{analysis['analysis_id']}/candidates/{second['id']}/exports"
        )
        sixty = wait(client, export.json()["status_url"])
        assert (
            sixty["status"] == "succeeded" and abs(sixty["result"]["media"]["duration"] - 60) <= 0.1
        )
        assert client.post(f"/analyses/{uuid4()}/candidates/{cid}/exports").status_code == 404
        publish_analysis_job(UUID(analysis["analysis_id"]), uuid4())
        # Same asset proves no second download (fixture copy would collide with saved audio).
        reused = submit(client, asset_id=analysis["asset_id"], purpose="humor")
        assert reused["status"] == "succeeded", reused
        with Session(get_engine()) as s:
            transcripts = list(
                s.scalars(
                    select(Transcript).where(Transcript.asset_id == UUID(analysis["asset_id"]))
                )
            )
            assert len(transcripts) == 1 and transcripts[0].state == "succeeded"
            calls = list(
                s.scalars(
                    select(ProviderCall).where(
                        ProviderCall.analysis_id == UUID(reused["analysis_id"])
                    )
                )
            )
            assert {c.stage for c in calls} == {"proposal", "scoring"}
            assert all(c.metadata_json["provider"] == "fixture" for c in calls)
        original = client.get(f"/analyses/{analysis['analysis_id']}").json()
        assert [c["id"] for c in original["candidates"]] == [
            c["id"] for c in analysis["candidates"]
        ]


def test_analysis_claim_interruption_and_transcript_claim():
    repo = AnalysisRepository()
    job = repo.create("https://fixture.example/analysis.mp4", None, "unknown", "balanced", {})
    repo.dispatch(job.id, lambda *args: None)
    with ThreadPoolExecutor(max_workers=4) as executor:
        claims = list(executor.map(lambda _: repo.claim(job.id), range(4)))
    assert sum(c is not None for c in claims) == 1
    assert repo.mark_interrupted(job.id, "Stopped fixture")
    assert not repo.finish(job.id, outcome="RECOMMENDED")
    assert repo.get(job.id).status == "failed"
    transcript, owner = repo.transcript(job.asset_id, "test-version")
    assert owner
    from app.domain.video import VideoError

    with pytest.raises(VideoError, match="전사"):
        repo.transcript(job.asset_id, "test-version")
    repo.save_transcript(transcript.id, [])
    reused, owner = repo.transcript(job.asset_id, "test-version")
    assert not owner and reused.segments == []


def test_transcription_only_then_recommendation_reuses_transcript():
    with httpx.Client(base_url=BASE, timeout=15) as client:
        result = submit(client, url="https://fixture.example/analysis.mp4", mode="transcription")
        assert result["outcome"] == "TRANSCRIBED" and result["candidates"] == []
        assert result["config"]["recommendation_provider"] == "none"
        assert result["config"]["model"] is None
        path = f"/analyses/{result['analysis_id']}/transcript"
        transcript = client.get(path).json()
        assert len(transcript["segments"]) == 36
        assert transcript["segments"][0]["start_ms"] == 0
        assert client.get(path).json() == transcript
        subtitles = client.get(f"/analyses/{result['analysis_id']}/subtitles").json()
        assert len(subtitles["cues"]) == 72 and not subtitles["review_required"]
        assert subtitles["cues"][0]["end_ms"] == 1500
        assert subtitles["cues"][1]["start_ms"] == 1600
        download = client.get(f"/analyses/{result['analysis_id']}/subtitles.srt")
        assert download.status_code == 200 and "00:00:01,600" in download.text
        assert client.get(path).json() == transcript
        assert client.get(f"/analyses/{uuid4()}/transcript").status_code == 404
        with Session(get_engine()) as s:
            calls = list(
                s.scalars(
                    select(ProviderCall).where(
                        ProviderCall.analysis_id == UUID(result["analysis_id"])
                    )
                )
            )
            assert [c.stage for c in calls] == ["transcription"]
        recommended = submit(client, asset_id=result["asset_id"], mode="recommendation")
        assert recommended["outcome"] == "RECOMMENDED"
        with Session(get_engine()) as s:
            calls = list(
                s.scalars(
                    select(ProviderCall).where(
                        ProviderCall.analysis_id == UUID(recommended["analysis_id"])
                    )
                )
            )
            assert {c.stage for c in calls} == {"proposal", "scoring"}


def test_transcription_browser_refresh_does_not_resubmit():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        posts, errors = [], []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/recommendations")
        expect(page.get_by_label("작업 선택")).to_have_value("transcription")
        page.get_by_label("영상 링크").fill("https://fixture.example/analysis.mp4")
        page.get_by_role("button", name="음성 전사 시작").click()
        expect(page.locator("#segments p")).to_have_count(36, timeout=90000)
        expect(page.locator("#analysis-state")).to_contain_text("추천 AI 호출 없음")
        expect(page.locator("#subtitle-cues p")).to_have_count(72)
        expect(page.locator("#subtitle-state")).to_contain_text("원본 전사 보존")
        with page.expect_download() as download:
            page.get_by_role("link", name="SRT 다운로드").click()
        assert download.value.failure() is None
        assert download.value.suggested_filename.endswith(".srt")
        page.locator("#transcript summary").click()
        expect(page.locator("#segments p").first).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if screenshot := os.getenv("SUBTITLE_SCREENSHOT_PATH"):
            page.screenshot(path=screenshot, full_page=True)
        page.reload()
        expect(page.locator("#segments p")).to_have_count(36)
        expect(page.locator("#subtitle-cues p")).to_have_count(72)
        assert len(posts) == 1 and not errors
        assert page.locator(".candidate").count() == 0
        browser.close()


def test_recommendation_browser_refresh_select_download():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors, posts = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        page.goto(BASE + "/recommendations")
        page.get_by_label("작업 선택").select_option("recommendation")
        page.get_by_label("영상 링크").fill("https://fixture.example/analysis.mp4")
        page.get_by_role("button", name="하이라이트 추천받기").click()
        expect(page.get_by_role("heading", name="1. 첫 이야기")).to_be_visible(timeout=90000)
        analysis_url = page.url
        page.reload()
        expect(page.get_by_role("heading", name="1. 첫 이야기")).to_be_visible()
        assert len(posts) == 1
        page.get_by_role("button", name="이 구간 추출하기").first.click()
        expect(page.get_by_role("heading", name="추천 구간 영상이 준비됐어요")).to_be_visible(
            timeout=90000
        )
        expect(page.locator("#preview")).to_be_visible()
        with page.expect_download() as download:
            page.get_by_role("button", name="MP4 다운로드").click()
        assert download.value.failure() is None
        page.goto(analysis_url)
        expect(page.get_by_role("link", name="추출 상태 · 미리보기 · 다운로드 →")).to_be_visible()
        assert len(posts) == 2
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors
        browser.close()


def test_recommendation_query_failure_and_safe_text():
    analysis_id = str(uuid4())
    data = {
        "analysis_id": analysis_id,
        "status": "succeeded",
        "stage": "complete",
        "analysis_basis": "전사 기반",
        "outcome": "RECOMMENDED",
        "candidates": [
            {
                "id": str(uuid4()),
                "rank": 1,
                "title": "<img src=x onerror=alert(1)>",
                "start_ms": 0,
                "end_ms": 30000,
                "score": 75,
                "reason": "테스트 이유",
                "scores": {"hook": 3},
                "segments": [{"text": "<script>alert(1)</script>"}],
                "evidence_ids": ["s0000"],
                "export_job_id": None,
            }
        ],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.route(f"**/analyses/{analysis_id}", lambda route: route.abort())
        page.goto(BASE + f"/recommendations?analysis={analysis_id}")
        expect(page.locator("#analysis-state")).to_contain_text("분석 실패를 의미하지 않습니다")
        page.unroute(f"**/analyses/{analysis_id}")
        page.route(f"**/analyses/{analysis_id}", lambda route: route.fulfill(json=data))
        page.get_by_role("button", name="상태 다시 조회").click()
        expect(page.locator(".candidate h3")).to_contain_text("<img src=x onerror=alert(1)>")
        assert page.locator(".candidate img, .candidate script").count() == 0
        browser.close()


def test_subtitle_query_error_keeps_analysis_complete_and_renders_review_safely():
    analysis_id = str(uuid4())
    data = {
        "analysis_id": analysis_id,
        "status": "succeeded",
        "stage": "complete",
        "analysis_basis": "전사 기반",
        "outcome": "TRANSCRIBED",
        "candidates": [],
        "config": {"mode": "transcription", "asr_version": "fixture"},
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        page.route(f"**/analyses/{analysis_id}", lambda r: r.fulfill(json=data))
        page.route(
            f"**/analyses/{analysis_id}/transcript", lambda r: r.fulfill(json={"segments": []})
        )
        page.route(f"**/analyses/{analysis_id}/subtitles", lambda r: r.abort())
        page.goto(BASE + f"/recommendations?analysis={analysis_id}")
        expect(page.locator("#subtitle-state")).to_contain_text("자막 조회에 실패")
        expect(page.locator("#analysis-state")).to_contain_text("전사 완료")
        expect(page.get_by_role("button", name="상태 다시 조회")).to_be_visible()
        page.unroute(f"**/analyses/{analysis_id}/subtitles")
        page.route(
            f"**/analyses/{analysis_id}/subtitles",
            lambda r: r.fulfill(
                json={
                    "review_required": True,
                    "cues": [
                        {
                            "start_ms": 0,
                            "end_ms": 21000,
                            "lines": ["<script>alert(1)</script>"],
                            "review_required": True,
                            "warnings": ["WORD_TIMESTAMPS_UNAVAILABLE", "DURATION_LIMIT"],
                        }
                    ],
                }
            ),
        )
        page.get_by_role("button", name="상태 다시 조회").click()
        expect(page.locator("#subtitle-cues")).to_contain_text("검토 필요: 단어 시각 없음")
        expect(page.locator("#subtitle-cues")).to_contain_text("<script>alert(1)</script>")
        assert page.locator("#subtitle-cues script").count() == 0 and not posts
        browser.close()
