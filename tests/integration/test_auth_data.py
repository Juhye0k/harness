"""Run only against a dedicated disposable database: AUTH_TEST_DATABASE_URL."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import auth
from app.api.auth import csrf, digest
from app.auth_models import AuthSession, Deletion, ResourceUse, User
from app.cli.cleanup_data import sweep
from app.config import get_settings
from app.db import get_engine
from app.main import app
from app.models import AnalysisJob, Asset, VideoJob, utcnow
from app.services.access import acquire, release

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("AUTH_TEST_DATABASE_URL"), reason="Dedicated auth database required"
    ),
]


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", os.environ["AUTH_TEST_DATABASE_URL"])
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("AUTH_ORIGIN", "http://testserver")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VIDEO_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = get_engine()
    token = str(uuid4())
    with Session(engine) as s, s.begin():
        a, b = User(state="active"), User(state="active")
        s.add_all([a, b])
        s.flush()
        aid, bid = a.id, b.id
        s.add(
            AuthSession(
                token_hash=digest(token),
                user_id=aid,
                expires_at=utcnow() + timedelta(days=7),
                reauthenticated_at=utcnow(),
            )
        )
        asset = Asset(
            source_url="https://example.com/private.mp4",
            user_id=bid,
            legacy=False,
            expires_at=utcnow() + timedelta(days=7),
        )
        s.add(asset)
        s.flush()
        analysis = AnalysisJob(asset_id=asset.id, genre="unknown", purpose="balanced", config={})
        s.add(analysis)
        job = VideoJob(
            source_url="https://example.com/private.mp4",
            start_seconds=0,
            user_id=bid,
            legacy=False,
            expires_at=asset.expires_at,
        )
        s.add(job)
        s.flush()
        ids = {"asset": asset.id, "analysis": analysis.id, "job": job.id}
    with TestClient(app) as client:
        client.cookies.set("shortform_session", token)
        client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": csrf(token)})
        yield client, engine, aid, bid, ids, tmp_path
    engine.dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "path",
    [
        "/jobs/{job}",
        "/jobs/{job}/download",
        "/analyses/{analysis}",
        "/analyses/{analysis}/transcript",
        "/analyses/{analysis}/subtitles.srt",
        "/analyses/{analysis}/review-audio",
        "/analyses/{analysis}/verification",
        "/assets/{asset}/deletion-preview",
    ],
)
def test_cross_user_read_denied(setup, path):
    client, _, _, _, ids, _ = setup
    assert client.get(path.format(**ids)).status_code == 404


def test_cross_user_side_effects_denied(setup):
    client, _, _, _, ids, _ = setup
    assert client.post("/analyses", json={"asset_id": str(ids["asset"])}).status_code == 404
    assert client.delete(f"/assets/{ids['asset']}").status_code == 404
    assert client.post("/sns/uploads", json={"job_id": str(ids["job"])}).status_code == 404


def test_sessions_csrf_and_logout(setup):
    client, _, _, _, _, _ = setup
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_delete_idempotent_and_scrub(setup):
    client, engine, user, _, _, root = setup
    with Session(engine) as s, s.begin():
        job = VideoJob(
            source_url="secret-url",
            start_seconds=0,
            user_id=user,
            legacy=False,
            status="succeeded",
            expires_at=utcnow() + timedelta(days=7),
        )
        s.add(job)
        s.flush()
        job_id = job.id
    directory = root / str(job_id)
    directory.mkdir()
    (directory / "clip.mp4").write_bytes(b"private")
    uses = acquire(user, [("job", job_id)], engine)
    assert client.delete(f"/jobs/{job_id}").status_code == 409
    release(uses, engine)
    first = client.delete(f"/jobs/{job_id}")
    assert first.status_code == 202, first.text
    assert client.delete(f"/jobs/{job_id}").json() == first.json()
    assert client.get(f"/jobs/{job_id}").status_code == 410
    sweep(engine, root)
    assert not directory.exists()
    assert client.get(first.json()["status_url"]).json()["state"] == "complete"
    with Session(engine) as s:
        assert s.get(VideoJob, job_id).source_url == ""


def test_expiry_and_legacy_preservation(setup):
    client, engine, user, _, _, root = setup
    with Session(engine) as s, s.begin():
        old = Asset(source_url="legacy")
        new = Asset(
            source_url="private",
            user_id=user,
            legacy=False,
            expires_at=utcnow() - timedelta(seconds=1),
        )
        s.add_all([old, new])
        s.flush()
        old_id, new_id = old.id, new.id
    assert client.get(f"/assets/{new_id}/deletion-preview").status_code == 410
    sweep(engine, root)
    with Session(engine) as s:
        assert s.get(Asset, old_id).source_url == "legacy"
        assert s.get(Asset, new_id).source_url == ""


def test_leave_has_restricted_status_token(setup):
    client, engine, user, _, _, root = setup
    result = client.delete("/auth/me")
    assert result.status_code == 202, result.text
    data = result.json()
    assert client.get("/assets").status_code == 401
    assert client.get(data["status_url"]).status_code == 404
    assert (
        client.get(data["status_url"], headers={"X-Deletion-Token": data["token"]}).status_code
        == 200
    )
    sweep(engine, root)
    with Session(engine) as s:
        assert s.get(User, user).state == "deleted"
        assert not s.scalar(select(ResourceUse.id).where(ResourceUse.user_id == user))
        assert s.scalar(select(Deletion).where(Deletion.user_id == user)).state == "complete"


def test_google_callback_pending_approval_and_replay(setup, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    client, engine, _, _, _, _ = setup
    monkeypatch.setenv("GOOGLE_LOGIN_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_LOGIN_CLIENT_SECRET", "not-a-real-secret")
    get_settings.cache_clear()
    subject = str(uuid4())
    monkeypatch.setattr(auth, "verify_google", lambda code, login: {"sub": subject})
    response = client.get("/auth/google/start", follow_redirects=False)
    assert response.status_code == 307
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    path = "/auth/google/callback?state=" + state + "&code=fake-code"
    callback = client.get(path, follow_redirects=False)
    assert "/login?pending=" in callback.headers["location"]
    assert client.get(path, follow_redirects=False).status_code == 400
    user_id = callback.headers["location"].split("pending=")[1]
    with Session(engine) as s, s.begin():
        s.get(User, __import__("uuid").UUID(user_id)).state = "active"
    response = client.get("/auth/google/start", follow_redirects=False)
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    callback = client.get(
        "/auth/google/callback?state=" + state + "&code=fake-code", follow_redirects=False
    )
    assert callback.headers["location"] == "/my-data"
    assert client.get("/auth/me").json()["user_id"] == user_id


def test_owned_download_range_and_new_job_owner(setup, monkeypatch):
    from app.api import jobs as api_jobs

    client, engine, user, _, _, root = setup
    monkeypatch.setattr(api_jobs, "publisher", lambda: lambda *args: None)
    result = client.post(
        "/jobs/video-extractions", json={"url": "https://media.w3.org/test.mp4", "start_seconds": 0}
    )
    assert result.status_code == 202, result.text
    job_id = __import__("uuid").UUID(result.json()["job_id"])
    directory = root / str(job_id)
    directory.mkdir()
    (directory / "clip.mp4").write_bytes(b"0123456789")
    with Session(engine) as s, s.begin():
        job = s.get(VideoJob, job_id)
        assert job.user_id == user and not job.legacy
        job.status = "succeeded"
        job.output_path = str(job_id) + "/clip.mp4"
    response = client.get(f"/jobs/{job_id}/download", headers={"Range": "bytes=2-4"})
    assert response.status_code == 206 and response.content == b"234"
    with Session(engine) as s:
        assert not s.scalar(select(ResourceUse.id).where(ResourceUse.user_id == user))


def test_expired_queued_job_is_not_left_pending(setup):
    _, engine, user, _, _, root = setup
    with Session(engine) as s, s.begin():
        job = VideoJob(
            source_url="private",
            start_seconds=0,
            user_id=user,
            legacy=False,
            status="queued",
            expires_at=utcnow() - timedelta(seconds=1),
        )
        s.add(job)
        s.flush()
        job_id = job.id
    sweep(engine, root)
    with Session(engine) as s:
        job = s.get(VideoJob, job_id)
        assert job.status == "failed" and job.source_url == ""


def test_real_browser_login_boundary_and_logout(setup, monkeypatch):
    import socket
    import sys
    import threading
    import time

    import uvicorn
    from playwright.sync_api import expect, sync_playwright

    client, _, _, _, ids, _ = setup
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("AUTH_ORIGIN", origin)
    get_settings.cache_clear()
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        with sync_playwright() as p:
            browser = p.chromium.launch(
                **({"channel": "msedge"} if sys.platform == "win32" else {})
            )
            context = browser.new_context()
            page = context.new_page()
            page.goto(origin + "/my-data")
            expect(page).to_have_url(origin + "/login")
            context.add_cookies(
                [
                    {
                        "name": "shortform_session",
                        "value": client.cookies.get("shortform_session"),
                        "url": origin,
                    }
                ]
            )
            page.evaluate("localStorage.setItem('previous-secret', 'old account')")
            page.goto(origin + "/my-data")
            expect(page.get_by_role("heading", name="내 자료", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="로그아웃", exact=True)).to_be_visible()
            assert page.evaluate("localStorage.getItem('previous-secret')") is None
            assert str(ids["asset"]) not in page.locator("main").inner_text()
            page.get_by_role("button", name="로그아웃", exact=True).click()
            expect(page).to_have_url(origin + "/login")
            page.goto(origin + "/my-data")
            expect(page).to_have_url(origin + "/login")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
