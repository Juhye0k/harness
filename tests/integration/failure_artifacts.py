"""Capture synthetic-only failure traces without replacing the original assertion."""

import json
from contextlib import contextmanager
from uuid import uuid4

from playwright.sync_api import sync_playwright

from app.config import get_settings


@contextmanager
def observed_browser(scenario):
    directory = get_settings().video_data_dir.parent / "e2e" / "failures" / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.tracing.start(screenshots=True, snapshots=True)
        page = context.new_page()
        requests = []
        page.on("request", lambda r: requests.append({"method": r.method, "url": r.url}))
        passed = False
        try:
            yield page
            passed = True
        finally:
            try:
                page.screenshot(path=str(directory / "screen.png"), full_page=True)
                context.tracing.stop(path=str(directory / "trace.zip"))
            finally:
                (directory / "summary.json").write_text(
                    json.dumps(
                        {
                            "scenario": scenario,
                            "passed": passed,
                            "providers": "fixtures",
                            "requests": requests,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                browser.close()
