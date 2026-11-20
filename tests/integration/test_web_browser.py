"""Browser regression tests plus the real video workflow; no external media access."""

import os
import re
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture worker required"),
]
BASE = os.getenv("TEST_API_URL", "http://api:8000")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    context.close()
    assert not errors, errors


def state(job_id, status):
    return {
        "job_id": job_id,
        "status": status,
        "error": {"message": "입력 구간이 원본을 넘습니다."} if status == "failed" else None,
        "result": {"media": {"duration": 10}},
        "download_url": f"/jobs/{job_id}/download",
    }


def test_real_browser_extract_reload_preview_download(page, tmp_path):
    posts = []
    page.on(
        "request", lambda request: posts.append(request.url) if request.method == "POST" else None
    )
    page.goto(BASE + "/extract")
    page.get_by_label("영상 링크", exact=True).fill("https://fixture.example/sample.mp4")
    page.get_by_label("시작 시간", exact=False).fill("5")
    page.get_by_role("button", name="10초 영상 만들기").click()
    expect(page).to_have_url(re.compile(r"\?job=[0-9a-f-]{36}$"))
    expect(page.get_by_role("heading", name="10초 영상이 준비됐어요")).to_be_visible(timeout=60000)
    page.wait_for_function("document.querySelector('video').readyState >= 1")
    assert page.locator("video").evaluate("v => v.duration") == pytest.approx(10, abs=0.1)
    page.reload()
    expect(page.get_by_role("heading", name="10초 영상이 준비됐어요")).to_be_visible()
    assert len(posts) == 1
    with page.expect_download() as download:
        page.get_by_role("button", name="MP4 다운로드").click()
    destination = tmp_path / "clip.mp4"
    download.value.save_as(destination)
    assert destination.read_bytes()[4:8] == b"ftyp"
    page.screenshot(path="/data/web-result.png", full_page=True)
    page.get_by_role("link", name="새 영상 추출하기").click()
    expect(page.get_by_role("button", name="10초 영상 만들기")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path="/data/web-mobile.png", full_page=True)


@pytest.mark.parametrize(
    "status,title",
    [
        ("pending", "접수 확인 중"),
        ("queued", "추출 대기 중"),
        ("running", "영상을 추출하고 있어요"),
        ("failed", "영상 추출에 실패했어요"),
    ],
)
def test_job_states(page, status, title):
    job_id = str(uuid4())
    page.route(f"**/jobs/{job_id}", lambda route: route.fulfill(json=state(job_id, status)))
    page.goto(f"{BASE}/?job={job_id}")
    expect(page.get_by_role("heading", name=title)).to_be_visible()
    expect(page.get_by_role("button", name="MP4 다운로드")).to_be_hidden()


def test_query_failure_is_not_processing_failure_and_can_retry(page):
    job_id = str(uuid4())
    requests = []

    def respond(route):
        requests.append(route.request.url)
        if len(requests) == 1:
            route.abort()
        else:
            route.fulfill(json=state(job_id, "running"))

    page.route(f"**/jobs/{job_id}", respond)
    page.goto(f"{BASE}/?job={job_id}")
    expect(page.get_by_text("상태를 조회하지 못했어요.", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="영상 추출에 실패했어요")).to_be_hidden()
    page.get_by_role("button", name="상태 다시 조회").click()
    expect(page.get_by_role("heading", name="영상을 추출하고 있어요")).to_be_visible()


def test_submit_guard_and_validation_error(page):
    pending = []
    page.route("**/jobs/video-extractions", lambda route: pending.append(route))
    page.goto(BASE + "/extract")
    page.get_by_label("영상 링크", exact=True).fill("https://fixture.example/sample.mp4")
    page.get_by_role("button", name="10초 영상 만들기").click()
    expect(page.get_by_role("button", name="작업 접수 중")).to_be_disabled()
    page.locator("form").evaluate("form => form.requestSubmit()")
    assert len(pending) == 1
    pending[0].fulfill(status=422, json={"error": {"message": "invalid"}})
    expect(page.get_by_text("영상 링크와 시작 시간을 확인해 주세요.")).to_be_visible()
    expect(page.get_by_role("button", name="10초 영상 만들기")).to_be_enabled()


def test_unknown_submission_not_retried(page):
    requests = []

    def fail(route):
        requests.append(route.request.url)
        route.abort()

    page.route("**/jobs/video-extractions", fail)
    page.goto(BASE + "/extract")
    page.get_by_label("영상 링크", exact=True).fill("https://fixture.example/sample.mp4")
    page.get_by_role("button", name="10초 영상 만들기").click()
    expect(page.get_by_text("작업이 등록됐을 수도", exact=False)).to_be_visible()
    assert len(requests) == 1


def test_dispatch_error_with_id_opens_existing_job(page):
    job_id = str(uuid4())
    page.route(
        "**/jobs/video-extractions",
        lambda route: route.fulfill(
            status=503,
            json={"job_id": job_id, "error": {"code": "DISPATCH_FAILED"}},
        ),
    )
    page.route(f"**/jobs/{job_id}", lambda route: route.fulfill(json=state(job_id, "failed")))
    page.goto(BASE + "/extract")
    page.get_by_label("영상 링크", exact=True).fill("https://fixture.example/sample.mp4")
    page.get_by_role("button", name="10초 영상 만들기").click()
    expect(page).to_have_url(f"{BASE}/extract?job={job_id}")
    expect(page.get_by_role("heading", name="영상 추출에 실패했어요")).to_be_visible()


def test_history_navigation_restores_job_without_post(page):
    first, second = str(uuid4()), str(uuid4())
    posts = []
    page.on(
        "request", lambda request: posts.append(request.url) if request.method == "POST" else None
    )
    page.route(f"**/jobs/{first}", lambda route: route.fulfill(json=state(first, "running")))
    page.route(f"**/jobs/{second}", lambda route: route.fulfill(json=state(second, "failed")))
    page.goto(f"{BASE}/?job={first}")
    expect(page.get_by_role("heading", name="영상을 추출하고 있어요")).to_be_visible()
    page.evaluate(
        """id => {
            history.pushState(null, '', '/?job=' + id);
            dispatchEvent(new PopStateEvent('popstate'));
        }""",
        second,
    )
    expect(page.get_by_role("heading", name="영상 추출에 실패했어요")).to_be_visible()
    page.go_back()
    expect(page.locator("#job-id")).to_have_text(first)
    expect(page.get_by_role("heading", name="영상을 추출하고 있어요")).to_be_visible()
    assert not posts


@pytest.mark.parametrize(
    "job_id,title",
    [("bad-id", "작업 주소가 올바르지 않아요"), (str(uuid4()), "작업을 찾을 수 없어요")],
)
def test_invalid_or_missing_job(page, job_id, title):
    page.route("**/jobs/*", lambda route: route.fulfill(status=404, json={}))
    page.goto(f"{BASE}/?job={job_id}")
    expect(page.get_by_role("heading", name=title)).to_be_visible()


def test_missing_output_shows_download_error(page):
    job_id = str(uuid4())
    page.route(f"**/jobs/{job_id}", lambda route: route.fulfill(json=state(job_id, "succeeded")))
    page.route(f"**/jobs/{job_id}/download", lambda route: route.fulfill(status=410, json={}))
    page.goto(f"{BASE}/?job={job_id}")
    page.get_by_role("button", name="MP4 다운로드").click()
    expect(page.get_by_text("결과 파일을 찾을 수 없어요.", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="10초 영상이 준비됐어요")).to_be_visible()


def test_server_message_is_rendered_as_text(page):
    job_id = str(uuid4())
    data = state(job_id, "failed")
    data["error"]["message"] = '<img src=x onerror="window.injected=true">'
    page.route(f"**/jobs/{job_id}", lambda route: route.fulfill(json=data))
    page.goto(f"{BASE}/?job={job_id}")
    expect(page.locator("#job-description")).to_have_text(data["error"]["message"])
    assert page.locator("#job-description img").count() == 0
    assert not page.evaluate("Boolean(window.injected)")
