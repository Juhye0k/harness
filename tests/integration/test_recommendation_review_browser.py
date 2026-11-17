"""Synthetic manual-review flow in a real browser; no provider or account access."""

import json
import os
import socket
import time
from pathlib import Path
from threading import Thread

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from app.adapters.process import executable, run
from app.services.video import checksum
from scripts.evaluate_recommendations import Rating, Review, fingerprint, save_new
from scripts.review_recommendations import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1", reason="Explicit browser verification required"
    ),
]


def test_video_review_persists_and_prepares_offline_automation(tmp_path):
    source = tmp_path / "source.mp4"
    run(
        [
            executable("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "color=size=320x240:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        30,
    )
    transcript = {"segments": [{"id": "s0", "start_ms": 0, "end_ms": 1000, "text": "합성 입력"}]}
    snapshot = {
        "analysis_id": "synthetic",
        "status": "succeeded",
        "config": {"model": "fixture"},
        "evaluation_input": {
            "source_sha256": checksum(source),
            "duration_ms": 3000,
            "transcript_sha256": fingerprint(transcript["segments"]),
        },
        "candidates": [{"id": "c0", "start_ms": 0, "end_ms": 1000, "title": "합성 후보"}],
    }
    directory = tmp_path / "pack"
    review = Review(
        analysis_id="synthetic",
        split="development",
        snapshot_sha256=fingerprint(snapshot),
        ratings=[Rating(candidate_id="c0")],
    )
    for name, value in (
        ("snapshot.json", snapshot),
        ("review.json", review.model_dump()),
        ("transcript.json", transcript),
    ):
        save_new(directory / name, value)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(directory, source), log_level="error"))
    thread = Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        with sync_playwright() as p:
            options = {}
            if os.name == "nt":
                options["executable_path"] = str(
                    Path(os.environ["PROGRAMFILES"]) / "Google/Chrome/Application/chrome.exe"
                )
            browser = p.chromium.launch(**options)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(f"http://127.0.0.1:{port}")
            expect(page.get_by_role("heading", name="합성 후보")).to_be_visible()
            page.get_by_role("button", name="구간 재생", exact=True).click()
            page.wait_for_function("document.querySelector('video').currentTime > 0.1")
            page.evaluate(
                "document.querySelector('video').pause();"
                "document.querySelector('video').currentTime=0.2"
            )
            expect(page.locator("#caption-overlay")).to_have_text("합성 입력")
            expect(page.locator("#caption-overlay")).to_be_visible()
            page.get_by_label("검토용 자막 표시").uncheck()
            expect(page.locator("#caption-overlay")).to_be_hidden()
            expect(page.locator("#caption-text")).to_have_text("합성 입력")
            page.get_by_label("검토용 자막 표시").check()
            page.evaluate(
                "document.querySelector('video').pause();"
                "document.querySelector('video').currentTime=1.5"
            )
            expect(page.locator("#caption-overlay")).to_be_hidden()
            expect(page.locator("#caption-text")).to_have_text("이 시점에 표시할 전사가 없습니다.")
            page.evaluate("document.querySelector('video').currentTime=0.2")
            expect(page.locator("#caption-overlay")).to_be_visible()
            expect(page.locator("#caption-overlay")).to_have_text("합성 입력")
            page.get_by_label("평가자").fill("synthetic-reviewer")
            page.get_by_label("선택 여부").select_option("no")
            page.get_by_label("사용 가능 판정").select_option("yes")
            page.get_by_label("시작·끝의 자연스러움").select_option("4")
            page.get_by_label("원본 없이 이해 가능").select_option("4")
            # Saving also hashes the checkout. Wait for the POST on slow bind mounts
            # before asserting the UI result; preserve the acceptance assertions.
            with page.expect_response(
                lambda response: (
                    response.url.endswith("/api/review") and response.request.method == "POST"
                ),
                timeout=60000,
            ) as saved:
                page.get_by_role("button", name="평가 저장", exact=True).click()
            assert saved.value.status == 200
            expect(page.get_by_role("status")).to_contain_text("개선 분석")
            page.reload()
            expect(page.get_by_label("사용 가능 판정")).to_have_value("yes")
            expect(page.get_by_label("선택 여부")).to_have_value("no")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            response = page.request.get(
                f"http://127.0.0.1:{port}/media", headers={"Range": "bytes=0-31"}
            )
            assert response.status == 206 and len(response.body()) == 32
            stored = next(directory.glob("web-reviews/*/handoff.json"))
            assert json.loads(stored.read_text(encoding="utf-8"))["status"] == "ready_for_analysis"
            assert list(directory.glob("web-reviews/*/loop/session.json"))
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
