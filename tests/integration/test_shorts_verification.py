import os

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

from tests.integration.test_analysis_flow import BASE, submit

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture workers required"
    ),
]


def test_fast_policy_web_and_download_contract():
    with httpx.Client(base_url=BASE, timeout=20) as client:
        job = submit(client, url="https://fixture.example/analysis.mp4", mode="transcription")
        aid = job["analysis_id"]
        url = f"/analyses/{aid}"
        result = client.get(url + "/verification").json()
        fast = result["display"]
        assert fast["quality_pass"] and len(fast["cues"]) == 108
        assert result["transcript_human_review"]["status"] == "pending"
        assert client.get(url + "/subtitles.srt?profile=shorts-display-v1").status_code == 200
        before = client.get(url + "/transcript").json()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844})
            writes = []
            page.on("request", lambda r: writes.append(r.url) if r.method != "GET" else None)
            page.goto(BASE + f"/verification?analysis={aid}")
            expect(page.locator("#cues p")).to_have_count(108)
            expect(page.locator("#download")).to_be_visible()
            expect(page.locator("#states")).to_contain_text("표시 품질: 통과")
            page.reload()
            expect(page.locator("#cues p")).to_have_count(108)
            for width in (390, 768, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
                cards = page.locator("main > section").all()
                assert len(cards) == 3
                boxes = [card.bounding_box() for card in cards]
                for previous, current in zip(boxes, boxes[1:], strict=False):
                    assert current["y"] >= previous["y"] + previous["height"]
                # A desktop page must actually use the available width.
                assert boxes[0]["width"] >= width * 0.85
                assert page.locator("#lookup button").is_visible()

            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("#fullscreen").click()
            expect(page.locator("#fullscreen")).to_have_attribute("aria-pressed", "true")
            assert page.evaluate("document.fullscreenElement === document.documentElement")
            page.locator("#fullscreen").click()
            expect(page.locator("#fullscreen")).to_have_attribute("aria-pressed", "false")
            assert page.evaluate("document.fullscreenElement === null")

            # Download gating must survive the new layout and a fresh lookup.
            blocked = {**result, "display": {**fast, "quality_pass": False}}
            page.route("**/verification", lambda route: route.fulfill(json=blocked))
            page.locator("#lookup button").click()
            expect(page.locator("#download")).to_be_hidden()
            expect(page.locator("#states")).to_contain_text("표시 품질: 검수 필요")
            assert not writes
            browser.close()
        assert client.get(url + "/transcript").json() == before
