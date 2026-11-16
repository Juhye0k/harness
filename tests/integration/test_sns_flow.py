"""Real HTTP, DB, Redis, Celery and Chromium with a non-networking YouTube fixture."""

import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright
from redis import Redis

from app.config import get_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Fixture workers required"
    ),
]
BASE = os.getenv("TEST_API_URL", "http://api:8000")
ARTIFACTS = Path(os.getenv("TEST_ARTIFACT_DIR", "/data"))


def wait(client, path, terminal=("succeeded", "failed", "unknown")):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        response = client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] in terminal:
            return data
        time.sleep(0.2)
    pytest.fail(f"Timed out: {path}")


@pytest.fixture
def connected():
    with httpx.Client(base_url=BASE, timeout=20) as client:
        session = client.get("/sns/session")
        assert session.status_code == 200
        client.headers["X-SNS-CSRF"] = session.json()["csrf"]
        url = client.post("/sns/youtube/connect").json()["authorization_url"]
        state = parse_qs(urlsplit(url).query)["state"][0]
        # No browser visits Google. Only the explicit test API accepts fixture-code.
        response = client.get(
            "/sns/youtube/callback", params={"state": state, "code": "fixture-code"}
        )
        assert (
            response.status_code == 303 and response.headers["location"] == "/sns?oauth=connected"
        )
        account = client.get("/sns/accounts").json()[0]
        created = client.post(
            "/jobs/video-extractions",
            json={
                "url": "https://fixture.example/sample.mp4",
                "start_seconds": 2,
            },
        )
        assert created.status_code == 202, created.text
        job_id = created.json()["job_id"]
        assert wait(client, f"/jobs/{job_id}")["status"] == "succeeded"
        yield client, account, job_id


def draft(client, account, job_id, title="테스트 업로드"):
    response = client.post(
        "/sns/uploads",
        json={
            "request_id": str(uuid4()),
            "account_id": account["account_id"],
            "job_id": job_id,
            "title": title,
            "made_for_kids": False,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["approval"]["privacy"] == "private"
    return response.json()


def confirm(client, data):
    response = client.post(
        f"/sns/uploads/{data['upload_id']}/confirm",
        json={
            "confirmed": True,
            "approval": data["approval"],
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def counts(upload_id):
    with Redis.from_url(get_settings().redis_url, decode_responses=True) as client:
        return client.hgetall(f"sns-fixture:{upload_id}")


def test_http_approval_duplicate_and_oauth_security(connected):
    client, account, job_id = connected
    data = draft(client, account, job_id)
    assert not counts(data["upload_id"])  # Merely previewing cannot dispatch.
    for field, value in (("title", "새 제목"), ("privacy", "public")):
        response = client.post(
            f"/sns/uploads/{data['upload_id']}/confirm",
            json={
                "confirmed": True,
                "approval": {**data["approval"], field: value},
            },
        )
        assert response.status_code == 409
    with httpx.Client(base_url=BASE) as other:
        other.get("/sns/session")
        assert other.get(f"/sns/uploads/{data['upload_id']}").status_code == 404
        assert other.get("/sns/accounts").json() == []
    result = confirm(client, data)
    assert wait(client, f"/sns/uploads/{result['upload_id']}")["status"] == "succeeded"
    assert confirm(client, data)["upload_id"] == result["upload_id"]
    second = draft(client, account, job_id)
    assert confirm(client, second)["upload_id"] == result["upload_id"]
    assert counts(result["upload_id"])["sent"] == "1"
    assert counts(result["upload_id"])["privacy"] == "private"
    assert client.post(f"/sns/uploads/{result['upload_id']}/probe").status_code == 409
    # A different browser cannot consume state; the callback is one-shot.
    url = client.post("/sns/youtube/connect").json()["authorization_url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    params = {"state": state, "code": "fixture-code"}
    with httpx.Client(base_url=BASE) as other:
        other.get("/sns/session")
        assert (
            other.get("/sns/youtube/callback", params=params).headers["location"]
            == "/sns?oauth=error"
        )
    assert (
        client.get("/sns/youtube/callback", params=params).headers["location"]
        == "/sns?oauth=connected"
    )
    assert (
        client.get("/sns/youtube/callback", params=params).headers["location"] == "/sns?oauth=error"
    )
    assert "fixture-refresh" not in client.get("/sns/accounts").text


@pytest.mark.parametrize(
    "title,expected",
    [
        ("fixture-unknown", "unknown"),
        ("fixture-reject", "failed"),
        ("fixture-incomplete", "unknown"),
    ],
)
def test_ambiguous_result_only_probes_existing_session(connected, title, expected):
    client, account, job_id = connected
    data = draft(client, account, job_id, title)
    confirm(client, data)
    result = wait(client, f"/sns/uploads/{data['upload_id']}")
    assert result["status"] == expected
    assert confirm(client, data)["upload_id"] == data["upload_id"]
    if expected == "unknown":
        response = client.post(f"/sns/uploads/{data['upload_id']}/probe")
        assert response.status_code == 202, response.text
        deadline = time.monotonic() + 10
        while not counts(data["upload_id"]).get("probed") and time.monotonic() < deadline:
            time.sleep(0.1)
        if title == "fixture-unknown":
            assert (
                wait(client, f"/sns/uploads/{data['upload_id']}", ("succeeded",))["status"]
                == "succeeded"
            )
        else:
            assert client.get(f"/sns/uploads/{data['upload_id']}").json()["status"] == "unknown"
        assert counts(data["upload_id"])["probed"] == "1"
    assert counts(data["upload_id"])["sent"] == "1"
    assert counts(data["upload_id"])["initiated"] == "1"


def test_browser_explicit_confirmation_reload_and_query_error(connected):
    client, account, job_id = connected
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 1000})
        for cookie in client.cookies.jar:
            context.add_cookies(
                [
                    {
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": urlsplit(BASE).hostname,
                        "path": "/sns",
                        "httpOnly": True,
                        "sameSite": "Lax",
                    }
                ]
            )
        page = context.new_page()
        errors, posts = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda req: posts.append(req.url) if req.method == "POST" else None)
        page.goto(f"{BASE}/sns?job={job_id}")
        expect(page.get_by_label("YouTube 제목", exact=True)).to_be_visible()
        expect(page.get_by_label("공개 범위", exact=True)).to_have_value("private")
        page.get_by_label("YouTube 제목", exact=True).fill("브라우저 테스트 & 제목")
        page.get_by_label("아동용 콘텐츠인가요?").select_option("false")
        page.get_by_role("button", name="업로드 내용 미리 확인").dblclick()
        expect(page).to_have_url(re.compile(r"/sns\?upload=[a-f0-9-]{36}$"))
        expect(page.get_by_role("button", name="확인한 내용으로 YouTube에 업로드")).to_be_disabled()
        assert len(posts) == 1
        upload_id = parse_qs(urlsplit(page.url).query)["upload"][0]
        assert not counts(upload_id)
        expect(page.locator("video")).to_have_js_property("videoWidth", 160)
        page.screenshot(path=str(ARTIFACTS / "sns-review.png"), full_page=True)
        page.reload()
        expect(page.get_by_role("button", name="확인한 내용으로 YouTube에 업로드")).to_be_disabled()
        assert len(posts) == 1
        page.get_by_role("checkbox").check()
        page.get_by_role("button", name="확인한 내용으로 YouTube에 업로드").dblclick()
        expect(page.locator("#upload-state")).to_contain_text("업로드가 완료됐어요", timeout=30000)
        assert len([url for url in posts if url.endswith("/confirm")]) == 1
        assert counts(upload_id)["sent"] == "1"
        page.reload()
        expect(page.locator("#upload-state")).to_contain_text("업로드가 완료됐어요")
        assert len(posts) == 2
        page.route(f"**/sns/uploads/{upload_id}", lambda route: route.abort())
        page.reload()
        expect(page.locator("#notice")).to_contain_text("업로드 실패를 의미하지 않습니다")
        page.unroute(f"**/sns/uploads/{upload_id}")
        page.get_by_role("button", name="상태 다시 조회").click()
        expect(page.locator("#upload-state")).to_contain_text("업로드가 완료됐어요")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ARTIFACTS / "sns-mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()
