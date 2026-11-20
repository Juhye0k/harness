"""Browser-to-worker vertical slice. Only external media/AI/YouTube use fixtures."""

import hashlib
import json
import os
import re
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright
from redis import Redis

from app.config import get_settings
from tests.integration.test_analysis_flow import BASE

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture workers required"
    ),
]


def srt_time_ms(timestamp):
    hours, minutes, seconds, milliseconds = map(int, re.split("[:,]", timestamp))
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def test_input_to_edited_portrait_download_and_confirmed_upload():
    evidence = get_settings().video_data_dir.parent / "e2e" / "complete-flow" / uuid4().hex
    evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, accept_downloads=True
        )
        context.tracing.start(screenshots=True, snapshots=True)
        page = context.new_page()
        errors, posts = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        try:
            page.goto(BASE + "/")
            expect(page.get_by_label("작업 선택")).to_have_value("recommendation")
            page.get_by_label("영상 링크").fill("https://fixture.example/analysis.mp4")
            page.get_by_role("button", name="하이라이트 추천받기").dblclick()
            expect(page.locator(".edit-candidate")).to_have_count(2, timeout=90000)
            assert len([url for url in posts if url.endswith("/analyses")]) == 1
            aid = parse_qs(urlsplit(page.url).query)["analysis"][0]
            page.goto(BASE + "/")
            project = page.locator(f'#project-list a[href$="analysis={aid}"]')
            expect(project).to_contain_text("2개 후보")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(evidence / "studio-mobile.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.screenshot(path=str(evidence / "studio-desktop.png"))
            project.click()
            before = context.request.get(f"{BASE}/analyses/{aid}/transcript").json()
            analysis = context.request.get(f"{BASE}/analyses/{aid}").json()
            candidate = next(c for c in analysis["candidates"] if c["start_ms"] > 0)
            cid = candidate["id"]
            revisions = f"{BASE}/analyses/{aid}/candidates/{cid}/caption-revisions"
            selected = page.locator(f'.candidate-select[data-id="{cid}"]')
            selected.click()
            expect(selected).to_have_attribute("aria-pressed", "true")
            expect(page.locator("#clip-title")).to_have_text(candidate["title"])
            page.locator("#play-candidate").click()
            page.wait_for_function(
                "(start) => { const video = document.querySelector('#clip-preview'); "
                "return !video.paused && video.currentTime > start + 0.1; }",
                arg=candidate["start_ms"] / 1000,
            )
            page.reload()
            expect(selected).to_have_attribute("aria-pressed", "true")
            page.locator("#clip-edit").click()
            first_cue = page.locator("#caption-rows textarea").first
            reviewed = page.get_by_label("선택 후보의 모든 원 구간을 검토했고", exact=False)
            render = page.get_by_role("button", name="확정한 자막으로 영상 만들기")
            save = page.get_by_role("button", name="편집본 저장", exact=True)
            expect(first_cue).to_be_visible()
            first_cue.fill("수정\n자막")
            save.dblclick()
            expect(page.locator("#editor-message")).to_have_text("편집본을 저장했습니다.")
            assert len([url for url in posts if url.endswith("/caption-revisions")]) == 1
            draft_id = parse_qs(urlsplit(page.url).query)["revision"][0]
            expect(reviewed).not_to_be_checked()
            expect(render).to_be_disabled()
            page.reload()
            expect(first_cue).to_have_value("수정\n자막")
            expect(reviewed).not_to_be_checked()
            expect(render).to_be_disabled()
            expect(page.locator("#final-result")).to_be_hidden()
            assert not any(url.endswith("/exports") for url in posts)
            assert len([url for url in posts if url.endswith("/caption-revisions")]) == 1

            # In this synthetic test only, simulate review. Checking without saving stays blocked.
            reviewed.check()
            expect(render).to_be_disabled()
            save.dblclick()
            expect(page.locator("#editor-message")).to_have_text("편집본을 저장했습니다.")
            rid = parse_qs(urlsplit(page.url).query)["revision"][0]
            assert rid != draft_id
            draft = context.request.get(f"{revisions}/{draft_id}").json()
            saved = context.request.get(f"{revisions}/{rid}").json()
            assert draft["reviewed"] is False and draft["render_job_id"] is None
            assert saved["reviewed"] is True and saved["cues"] == draft["cues"]
            page.reload()
            expect(first_cue).to_have_value("수정\n자막")
            expect(reviewed).to_be_checked()
            assert len([url for url in posts if url.endswith("/caption-revisions")]) == 2

            # Both client guarding and server idempotency prevent duplicate rendering.
            pending = []
            page.route("**/caption-revisions/*/exports", lambda route: pending.append(route))
            render.dblclick()
            expect(first_cue).to_be_disabled()
            expect(save).to_be_disabled()
            assert len(pending) == 1
            pending[0].continue_()
            page.unroute("**/caption-revisions/*/exports")
            expect(page.locator("#final-result")).to_be_visible(timeout=90000)
            job_id = parse_qs(urlsplit(page.url).query)["job"][0]
            export_url = next(url for url in posts if url.endswith(f"/{rid}/exports"))
            assert len([url for url in posts if url.endswith(f"/{rid}/exports")]) == 1
            duplicate = context.request.post(export_url, data={})
            assert duplicate.status == 202 and duplicate.json()["job_id"] == job_id
            result = context.request.get(f"{BASE}/jobs/{job_id}").json()
            assert result["status"] == "succeeded" and all(result["result"]["checks"].values())
            assert result["result"]["render"]["revision_id"] == rid
            assert result["result"]["render"]["subtitle_time_origin"] == "clip"
            assert result["result"]["media"]["width"] == 720
            assert result["result"]["media"]["height"] == 1280
            assert result["result"]["media"]["has_audio"]
            assert abs(result["result"]["media"]["duration"] - result["duration_seconds"]) <= 0.1
            payload = context.request.get(f"{BASE}/jobs/{job_id}/download").body()
            assert payload[4:8] == b"ftyp"
            srt_response = context.request.get(f"{BASE}/jobs/{job_id}/subtitles.srt")
            assert srt_response.ok
            srt_bytes = srt_response.body()
            entries = srt_bytes.decode("utf-8").strip().split("\n\n")
            for index, (entry, cue) in enumerate(zip(entries, saved["cues"], strict=True), 1):
                number, interval, *lines = entry.splitlines()
                start, end = interval.split(" --> ")
                assert number == str(index)
                assert srt_time_ms(start) == cue["start_ms"] - candidate["start_ms"]
                assert srt_time_ms(end) == cue["end_ms"] - candidate["start_ms"]
                assert lines == cue["lines"]
            assert saved["cues"][0]["lines"] == ["수정", "자막"]
            assert context.request.get(f"{BASE}/analyses/{aid}/transcript").json() == before

            with page.expect_download() as downloaded:
                page.get_by_role("link", name="완성 MP4 다운로드").click()
            downloaded.value.save_as(evidence / "edited-clip.mp4")
            assert (
                hashlib.sha256((evidence / "edited-clip.mp4").read_bytes()).digest()
                == hashlib.sha256(payload).digest()
            )
            with page.expect_download() as downloaded:
                page.get_by_role("link", name="클립 SRT 다운로드").click()
            downloaded.value.save_as(evidence / "edited-clip.srt")
            assert (evidence / "edited-clip.srt").read_bytes() == srt_bytes
            page.reload()
            expect(page.locator("#final-result")).to_be_visible()
            assert len([url for url in posts if url.endswith(f"/{rid}/exports")]) == 1

            page.route(f"**/jobs/{job_id}", lambda route: route.abort())
            page.reload()
            expect(page.locator("#render-state")).to_contain_text("처리 실패를 의미하지 않습니다")
            expect(page.locator("#retry-render")).to_be_visible()
            page.unroute(f"**/jobs/{job_id}")
            page.get_by_role("button", name="출력 상태 다시 조회").click()
            expect(page.locator("#final-result")).to_be_visible()

            # A local edit invalidates final/SNS links but preserves the saved snapshot.
            first_cue.fill("다른 자막")
            expect(page.locator("#render-final")).to_be_disabled()
            expect(page.locator("#final-result")).to_be_hidden()
            page.reload()
            expect(page.locator("#final-result")).to_be_visible()
            expect(first_cue).to_have_value("수정\n자막")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(evidence / "editor-mobile.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("#back").click()
            expect(selected).to_have_attribute("aria-pressed", "true")
            expect(page.locator("#clip-download")).to_have_attribute(
                "href", f"/jobs/{job_id}/download"
            )
            expect(page.locator("#clip-srt")).to_be_visible()
            page.get_by_role("link", name="YouTube 업로드", exact=True).click()

            # Exercise OAuth's real state/cookie exchange without visiting an external account.
            def fixture_oauth(route):
                state = parse_qs(urlsplit(route.request.url).query)["state"][0]
                route.fulfill(
                    status=302,
                    headers={
                        "Location": f"{BASE}/sns/youtube/callback?state={state}&code=fixture-code"
                    },
                )

            page.route("https://accounts.google.com/**", fixture_oauth)
            page.get_by_role("button", name="YouTube 계정 연결", exact=False).click()
            expect(page.locator("#upload-form")).to_be_visible()
            expect(page.locator("#job")).to_have_value(job_id)
            expect(page.get_by_label("YouTube 제목", exact=True)).to_have_value(candidate["title"])
            expect(page.locator("#sns-back")).to_have_attribute(
                "href", f"/editor?analysis={aid}&candidate={cid}&revision={rid}"
            )
            page.get_by_label("YouTube 제목", exact=True).fill("편집한 자막 E2E")
            page.get_by_label("아동용 콘텐츠인가요?").select_option("false")
            page.get_by_role("button", name="업로드 내용 미리 확인").click()
            expect(page).to_have_url(re.compile(r"/sns\?.*[?&]upload=[a-f0-9-]{36}$"))
            upload_query = parse_qs(urlsplit(page.url).query)
            upload_id = upload_query["upload"][0]
            assert upload_query["job"] == [job_id]
            assert upload_query["analysis"] == [aid]
            assert upload_query["candidate"] == [cid]
            assert upload_query["revision"] == [rid]
            expect(page.locator("#confirm")).to_be_disabled()
            with Redis.from_url(get_settings().redis_url, decode_responses=True) as redis:
                assert not redis.hgetall("sns-fixture:" + upload_id)
            page.reload()
            expect(page.locator("#confirm")).to_be_disabled()
            expect(page.locator("#sns-back")).to_have_attribute(
                "href", f"/editor?analysis={aid}&candidate={cid}&revision={rid}"
            )
            page.get_by_role("checkbox").check()
            page.get_by_role("button", name="확인한 내용으로 YouTube에 업로드").dblclick()
            expect(page.locator("#upload-state")).to_contain_text(
                "업로드가 완료됐어요", timeout=60000
            )
            with Redis.from_url(get_settings().redis_url, decode_responses=True) as redis:
                sent = redis.hgetall("sns-fixture:" + upload_id)
                assert sent["sent"] == "1" and sent["sha256"] == hashlib.sha256(payload).hexdigest()
                assert sent["privacy"] == "private"
            page.reload()
            expect(page.locator("#upload-state")).to_contain_text("업로드가 완료됐어요")
            assert len([url for url in posts if url.endswith("/confirm")]) == 1
            assert not errors, errors
            (evidence / "summary.json").write_text(
                json.dumps(
                    {
                        "flow": "passed",
                        "external_providers": "fixtures",
                        "real_infrastructure": True,
                        "revision_id": rid,
                        "job_id": job_id,
                        "render_profile": result["result"]["render"]["profile"],
                        "mp4_sha256": hashlib.sha256(payload).hexdigest(),
                        "srt_sha256": hashlib.sha256(srt_bytes).hexdigest(),
                        "upload_id": upload_id,
                        "posts": posts,
                        "page_errors": errors,
                    },
                    indent=2,
                )
            )
        except BaseException:
            page.screenshot(path=str(evidence / "failure.png"), full_page=True)
            raise
        finally:
            context.tracing.stop(path=str(evidence / "trace.zip"))
            browser.close()
