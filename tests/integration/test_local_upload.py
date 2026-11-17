"""Authenticated upload boundaries plus the real queue/browser local-file flow."""

import os
import time
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.upload_repository import UploadRepository
from app.api import uploads
from app.api.auth import csrf, digest
from app.auth_models import AuthSession, User
from app.config import get_settings
from app.db import get_engine
from app.main import app
from app.models import Asset, utcnow
from app.services.uploads import validate_upload

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("AUTH_TEST_DATABASE_URL"), reason="Dedicated database required"
    ),
]


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", os.environ["AUTH_TEST_DATABASE_URL"])
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUTH_ORIGIN", "http://testserver")
    monkeypatch.setenv("VIDEO_DATA_DIR", str(tmp_path / "originals"))
    monkeypatch.setenv("UPLOAD_DATA_DIR", str(tmp_path / "inbox"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = get_engine()
    with Session(engine) as s, s.begin():
        user = User(state="active")
        s.add(user)
        s.flush()
        uid = user.id
        token = str(uid)
        s.add(
            AuthSession(
                token_hash=digest(token), user_id=uid, expires_at=utcnow() + timedelta(days=7)
            )
        )
    app.dependency_overrides[uploads.publisher] = lambda: lambda *args: None
    with TestClient(app) as client:
        client.cookies.set("shortform_session", token)
        client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": csrf(token)})
        yield client, engine, uid, get_settings()
    app.dependency_overrides.pop(uploads.publisher, None)
    engine.dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def init(client, size):
    response = client.post("/assets/uploads", json={"size_bytes": size})
    assert response.status_code == 201, response.text
    return response.json()


def send(client, item, payload):
    return client.put(
        item["upload_url"], content=payload, headers={"Content-Type": "application/octet-stream"}
    )


@pytest.mark.parametrize("size", [0, -1, 524288001, True])
def test_declared_upload_limit(local, size):
    client, *_ = local
    assert client.post("/assets/uploads", json={"size_bytes": size}).status_code == 422


def test_streaming_over_json_limit_duplicate_and_worker_failure(local):
    client, engine, user, settings = local
    payload = b"invalid-media" * 12000
    item = init(client, len(payload))
    assert send(client, item, payload).status_code == 202
    assert send(client, item, payload).status_code == 409
    assert client.get(item["status_url"]).json()["status"] == "queued"
    validate_upload(UUID(item["asset_id"]), UploadRepository(engine), settings)
    status = client.get(item["status_url"]).json()
    assert status["status"] == "failed" and status["error_code"] == "INVALID_MEDIA"
    with Session(engine) as s:
        row = s.get(Asset, UUID(item["asset_id"]))
        assert row.user_id == user and not row.legacy
        assert row.expires_at - row.created_at <= timedelta(days=7, seconds=1)


def test_wrong_size_and_other_user_are_rejected(local):
    client, engine, _, _ = local
    item = init(client, 5)
    assert send(client, item, b"wrong-size").status_code == 413
    # No bytes have been accepted, so a correctly sized upload is still possible.
    assert send(client, item, b"12345").status_code == 202
    with Session(engine) as s, s.begin():
        other = User(state="active")
        s.add(other)
        s.flush()
        token = str(other.id)
        s.add(
            AuthSession(
                token_hash=digest(token), user_id=other.id, expires_at=utcnow() + timedelta(days=7)
            )
        )
    client.cookies.set("shortform_session", token)
    client.headers["X-CSRF-Token"] = csrf(token)
    assert client.get(item["status_url"]).status_code == 404
    assert send(client, item, b"12345").status_code == 404


def test_chunked_size_is_enforced_without_content_length(local):
    client, engine, _, settings = local
    item = init(client, 3)
    response = client.put(
        item["upload_url"],
        content=iter([b"ab", b"cd"]),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413
    assert client.get(item["status_url"]).json()["status"] == "failed"
    assert not (settings.upload_data_dir / item["asset_id"] / "receiving.part").exists()


def test_disconnected_transfer_marks_failure_and_removes_partial(local):
    from functools import partial

    import anyio
    from starlette.requests import ClientDisconnect, Request

    client, engine, _, settings = local
    item = init(client, 10)
    events = iter(
        [
            {"type": "http.request", "body": b"partial", "more_body": True},
            {"type": "http.disconnect"},
        ]
    )

    async def disconnected():
        return next(events)

    request = Request(
        {
            "type": "http",
            "method": "PUT",
            "path": item["upload_url"],
            "headers": [(b"content-type", b"application/octet-stream")],
        },
        disconnected,
    )
    with pytest.raises(ClientDisconnect):
        anyio.run(
            partial(
                uploads.receive,
                UUID(item["asset_id"]),
                request,
                UploadRepository(engine),
                lambda *args: None,
            )
        )
    row = client.get(item["status_url"]).json()
    assert row["status"] == "failed" and row["error_code"] == "UPLOAD_INTERRUPTED"
    assert not (settings.upload_data_dir / item["asset_id"] / "receiving.part").exists()


@pytest.mark.skipif(
    os.getenv("RUN_VIDEO_INTEGRATION") != "1", reason="Actual fixture workers required"
)
def test_browser_upload_extract_and_analysis(tmp_path):
    from playwright.sync_api import expect, sync_playwright

    from app.adapters.process import executable, run

    path = tmp_path / "local.mp4"
    run(
        [
            executable("ffmpeg"),
            "-v",
            "error",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=30:duration=180",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=180",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(path),
        ],
        60,
    )
    base = os.getenv("TEST_API_URL", "http://api:8000")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        posts = []
        page.on(
            "request", lambda req: posts.append(req.url) if req.method in {"POST", "PUT"} else None
        )
        page.goto(base + "/")
        page.get_by_label("업로드할 영상 파일").set_input_files(str(path))
        page.get_by_role("button", name="선택한 파일 업로드", exact=True).click()
        expect(
            page.get_by_text(
                "원본 검증 완료. 시작 시간이나 분석 조건을 정하고 실행하세요.", exact=True
            )
        ).to_be_visible(timeout=60000)
        asset = page.evaluate("window.uploadedAssetId")
        count = len(posts)
        page.reload()
        expect(
            page.get_by_text(
                "원본 검증 완료. 시작 시간이나 분석 조건을 정하고 실행하세요.", exact=True
            )
        ).to_be_visible(timeout=15000)
        assert len(posts) == count
        page.get_by_label("시작 시간").fill("5")
        page.get_by_role("button", name="10초 영상 만들기").click()
        expect(page.locator("#result")).to_be_visible(timeout=60000)
        assert "10.0초" in page.locator("#result-info").inner_text()
        browser.close()
    with httpx.Client(base_url=base, timeout=15) as client:
        result = client.post("/analyses", json={"mode": "transcription", "asset_id": asset})
        assert result.status_code == 202, result.text
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            data = client.get(result.json()["status_url"]).json()
            if data["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.3)
        assert data["status"] == "succeeded", data
        assert client.get(f"/assets/{asset}/upload").json()["status"] == "ready"
