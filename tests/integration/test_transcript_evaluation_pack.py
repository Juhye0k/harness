"""Offline reference-entry pack in a real browser; no external network or AI."""

import functools
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import expect, sync_playwright

from app.adapters.process import executable, run
from app.cli.evaluate_transcript import main
from app.domain.transcript_evaluation import evaluate

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Explicit browser run required"),
]


def test_listening_and_reference_download_can_be_evaluated(tmp_path):
    report = {
        "analysis_id": "synthetic",
        "transcript_version": "fixture-asr",
        "policy_version": "v1",
        "segments": [
            {
                "id": "s0",
                "start_ms": 0,
                "end_ms": 1000,
                "text": "사과",
                "quality": {},
                "recognition_reasons": [],
                "display_reasons": [],
                "priority": "none",
            }
        ],
    }
    input_file = tmp_path / "report.json"
    input_file.write_text(json.dumps(report), encoding="utf-8")
    audio = tmp_path / "fixture.mp3"
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
            "sine=duration=3",
            "-c:a",
            "libmp3lame",
            str(audio),
        ],
        15,
    )
    main(["--report", str(input_file), "--audio", str(audio), "--output", str(tmp_path / "pack")])

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(tmp_path))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            options = {}
            if os.name == "nt":
                options["executable_path"] = str(
                    Path(os.environ["PROGRAMFILES"]) / "Google/Chrome/Application/chrome.exe"
                )
            browser = p.chromium.launch(**options)
            page = browser.new_page(accept_downloads=True)
            page.goto(f"http://127.0.0.1:{server.server_port}/pack/review.html")
            expect(page.locator("article")).to_have_count(1)
            page.get_by_role("button", name="앞뒤 2초 듣기").click()
            page.wait_for_function("document.querySelector('audio').currentTime > 0.1")
            page.get_by_label("s0 인식 판정").select_option("error")
            page.get_by_label("s0 정답 전사").fill("사자")
            page.get_by_label("원음 확인 완료").check()
            with page.expect_download() as download:
                page.get_by_role("button", name="정답·판정 JSON 저장").click()
            path = tmp_path / "reviewed.json"
            download.value.save_as(path)
            refs = json.loads(path.read_text(encoding="utf-8"))
            result = evaluate(report, refs)
            assert result["cer"] == 0.5
            assert result["recognition_detector"]["false_negative"] == 1
            assert result["recognition_detector"]["recall"] == 0
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
