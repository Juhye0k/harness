import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import httpx
from playwright.sync_api import expect, sync_playwright

from app.adapters.analysis_repository import AnalysisRepository
from app.config import get_settings
from tests.integration.test_analysis_flow import BASE, pytestmark, submit  # noqa: F401


def test_cached_observations_reach_editor_and_conditional_save_preserves_latest():
    with httpx.Client(base_url=BASE, timeout=20) as client:
        first = submit(client)
        assert first["status"] == "succeeded", first
        asset = AnalysisRepository().asset(UUID(first["asset_id"]))
        root = get_settings().video_data_dir
        path = root / "assets" / str(asset.id) / "caption-observations.json"
        observation = {
            "schema_version": "source-caption-ocr-v1",
            "source_sha256": asset.sha256,
            "sample_step_ms": 100,
            "frames": [
                {"time_ms": point, "text": "개울 풍경" if point < 1600 else "완료 단계"}
                for point in range(0, 30500, 100)
            ],
        }
        path.write_text(json.dumps(observation), encoding="utf-8")
        analysis = submit(client, asset_id=str(asset.id), purpose="humor")
        assert analysis["status"] == "succeeded", analysis
        candidate, other = analysis["candidates"]
        assert "caption_draft" not in candidate
        aid, cid = analysis["analysis_id"], candidate["id"]
        base = f"/analyses/{aid}/candidates/{cid}"
        editor = client.get(base + "/editor").json()
        assert editor["alignment"]["status"] == "aligned", editor["alignment"]
        assert editor["suggested"]["review_required"] and editor["latest_revision"] is None
        fallback = client.get(f"/analyses/{aid}/candidates/{other['id']}/editor").json()
        assert fallback["alignment"]["status"] == "observations_unavailable"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            posts = []
            page.on(
                "request",
                lambda request: posts.append(request.url) if request.method == "POST" else None,
            )
            page.goto(f"{BASE}/editor?analysis={aid}&candidate={cid}")
            expect(page.locator("#draft-status")).to_contain_text("화면 전환과 전사 단어 시각")
            expect(page.locator("#render-final")).to_be_disabled()
            page.reload()
            expect(page.locator("#draft-status")).to_contain_text("화면 전환과 전사 단어 시각")
            assert not posts
            browser.close()

        body = {
            "source_version": editor["source_version"],
            "cues": editor["suggested"]["cues"],
            "expected_latest_revision_id": None,
            "reviewed": False,
        }
        competing = {
            **body,
            "cues": [{**body["cues"][0], "lines": ["다른 문구"]}, *body["cues"][1:]],
        }
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda data: client.post(base + "/caption-revisions", json=data),
                    [body, competing],
                )
            )
        assert sorted(response.status_code for response in responses) == [201, 409]
        saved_pos = 0 if responses[0].status_code == 201 else 1
        saved, conflict = responses[saved_pos].json(), responses[1 - saved_pos].json()
        assert conflict["error"]["code"] == "REVISION_CONFLICT"
        assert not saved["reviewed"] and saved["render_job_id"] is None
        revision = saved["revision_id"]
        winner = [body, competing][saved_pos]
        assert (
            client.post(base + "/caption-revisions", json=winner).json()["revision_id"] == revision
        )
        replacement = {**[competing, body][saved_pos], "expected_latest_revision_id": revision}
        next_saved = client.post(base + "/caption-revisions", json=replacement)
        assert next_saved.status_code == 201, next_saved.text
        current = client.get(base + "/editor").json()
        assert current["previous_revision_id"] == revision
        assert current["latest_revision"]["revision_id"] == next_saved.json()["revision_id"]
        assert client.get(base + f"/caption-revisions/{revision}").json() == saved


def test_editor_can_update_an_existing_legacy_export():
    analysis, candidate, revision, old_job, new_job = [str(uuid4()) for _ in range(5)]
    base = f"/analyses/{analysis}/candidates/{candidate}"
    cue = {"start_ms": 0, "end_ms": 1000, "lines": ["한글"], "source_segment_id": "s0000"}
    saved = {
        "revision_id": revision,
        "source_version": "fixture",
        "reviewed": True,
        "render_job_id": old_job,
        "render_profile": "portrait-edited-v1",
        "cues": [cue],
    }
    data = {
        "analysis_id": analysis,
        "candidate_id": candidate,
        "title": "테스트",
        "start_ms": 0,
        "end_ms": 1000,
        "source_version": "fixture",
        "segments": [{"id": "s0000", "text": "한글"}],
        "latest_revision": saved,
        "export_profile": "portrait-edited-v2",
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route(f"**{base}/editor", lambda route: route.fulfill(json=data))
        page.route(
            f"**/jobs/{old_job}",
            lambda route: route.fulfill(
                json={
                    "status": "succeeded",
                    "result": {
                        "render": {"revision_id": revision, "profile": "portrait-edited-v1"}
                    },
                    "download_url": f"/jobs/{old_job}/download",
                }
            ),
        )
        exports = []

        def accept(route):
            exports.append(route.request.post_data_json)
            route.fulfill(json={"job_id": new_job, "render_profile": "portrait-edited-v2"})

        page.route(f"**{base}/caption-revisions/{revision}/exports", accept)
        page.route(f"**/jobs/{new_job}", lambda route: route.fulfill(json={"status": "running"}))
        page.goto(f"{BASE}/editor?analysis={analysis}&candidate={candidate}")
        expect(page.locator("#render-state")).to_contain_text("이전 화면 구성")
        expect(page.locator("#final-download")).to_have_attribute(
            "href", f"/jobs/{old_job}/download"
        )
        expect(page.locator("#render-final")).to_be_enabled()
        page.locator("#render-final").click()
        expect(page.locator("#render-state")).to_contain_text("만드는 중")
        expect(page.locator("#final-result")).to_be_hidden()
        expect(page.locator("#render-final")).to_be_disabled()
        assert exports == [{}]
        browser.close()
