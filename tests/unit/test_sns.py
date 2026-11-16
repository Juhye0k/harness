import logging
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.adapters.sns_logging import GoogleHttpFilter, SnsAccessFilter
from app.adapters.youtube_upload import (
    SCOPES,
    ProviderFailure,
    TokenCipher,
    YouTubeProvider,
    authorization_url,
    session_url,
)
from app.api import sns as api
from app.config import Settings, get_settings
from app.domain.sns import SnsError, approval_values, output_version, validate_title
from app.main import app
from app.models import utcnow
from app.services.sns import process_upload, public_upload


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        app_env="test",
        sns_origin="http://testserver",
        enable_sns_upload=True,
        youtube_client_id="fake-client",
        youtube_client_secret="fake-secret",
        sns_token_key=Fernet.generate_key().decode(),
        video_data_dir=tmp_path,
    )


class WorkerRepository:
    def __init__(self, settings):
        self.path = settings.video_data_dir / "clip.mp4"
        self.path.write_bytes(b"approved output bytes")
        self.upload = SimpleNamespace(
            id=uuid4(),
            account_id=uuid4(),
            account_version=1,
            job_id=uuid4(),
            title="제목",
            privacy="private",
            made_for_kids=False,
            channel_id="channel-1",
            channel_title="<script>channel</script>",
            output_version=output_version(self.path),
            output_size=self.path.stat().st_size,
            status="queued",
            confirmed_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=15),
            error_code=None,
            remote_id=None,
            session_uri=None,
        )
        self.account_value = SimpleNamespace(
            version=1,
            channel_id="channel-1",
            credentials=TokenCipher(settings).encrypt({"refresh_token": "fake-refresh"}),
        )
        self.finishes = []

    def claim(self, upload_id):
        if self.upload.status != "queued" or not self.upload.confirmed_at:
            return None
        self.upload.status = "running"
        return self.upload

    def output(self, job_id):
        return SimpleNamespace(output_path="clip.mp4")

    def account(self, account_id):
        return self.account_value

    def record_session(self, upload_id, uri):
        self.upload.session_uri = uri
        return True

    def finish(self, upload_id, status, **values):
        self.finishes.append((status, values))
        self.upload.status = status
        for key, value in values.items():
            setattr(self.upload, key, value)


class FakeProvider:
    def __init__(self, failure=None):
        self.calls, self.failure, self.sent = [], failure, None

    def access_token(self, credentials):
        self.calls.append("token")
        return "fake-access"

    def channel(self, token):
        return {"id": "channel-1"}

    def initiate(self, token, upload, size):
        self.calls.append("initiate")
        return "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=fake"

    def send(self, token, uri, stream, size):
        self.calls.append("send")
        self.sent = stream.read()
        if self.failure:
            raise self.failure
        return "abcdefghijk"


def test_upload_uses_frozen_approved_bytes_and_records_session(settings):
    repo = WorkerRepository(settings)
    provider = FakeProvider()
    initial = provider.initiate

    def change_source(*args):
        repo.path.write_bytes(b"replacement after approval")
        return initial(*args)

    provider.initiate = change_source
    process_upload(repo.upload.id, repo, settings, provider)
    assert provider.sent == b"approved output bytes"
    assert repo.upload.status == "succeeded"
    assert "googleapis" not in repo.upload.session_uri
    assert TokenCipher(settings).decrypt(repo.upload.session_uri).startswith("https://")
    public = str(public_upload(repo.upload))
    assert "fake-access" not in public and "fake-refresh" not in public
    assert "session_uri" not in public and "credentials" not in public


@pytest.mark.parametrize("change", ["bytes", "account", "disabled", "unconfirmed"])
def test_stale_or_unapproved_upload_never_calls_provider(settings, change):
    repo, provider = WorkerRepository(settings), FakeProvider()
    if change == "bytes":
        repo.path.write_bytes(b"changed")
    elif change == "account":
        repo.account_value.version = 2
    elif change == "disabled":
        settings.enable_sns_upload = False
    else:
        repo.upload.confirmed_at = None
    process_upload(repo.upload.id, repo, settings, provider)
    assert not provider.calls
    assert repo.upload.status == ("queued" if change == "unconfirmed" else "failed")


@pytest.mark.parametrize("state", ["running", "unknown", "succeeded", "failed", "draft"])
def test_redelivery_does_not_publish_again(settings, state):
    repo, provider = WorkerRepository(settings), FakeProvider()
    repo.upload.status = state
    process_upload(repo.upload.id, repo, settings, provider)
    assert not provider.calls and not repo.finishes


@pytest.mark.parametrize(
    "failure,status",
    [
        (ProviderFailure(ambiguous=True), "unknown"),
        (ProviderFailure(ambiguous=False), "failed"),
        (RuntimeError("raw-secret"), "unknown"),
    ],
)
def test_send_failure_never_retries_or_exposes_raw_error(settings, failure, status, caplog):
    repo, provider = WorkerRepository(settings), FakeProvider(failure)
    process_upload(repo.upload.id, repo, settings, provider)
    assert repo.upload.status == status
    assert provider.calls.count("send") == 1
    process_upload(repo.upload.id, repo, settings, provider)
    assert provider.calls.count("send") == 1
    assert "raw-secret" not in caplog.text + str(public_upload(repo.upload))


@pytest.mark.parametrize("title", ["", "  ", "<title>", "title\nnext", "x" * 101])
def test_youtube_title_validation(title):
    with pytest.raises(SnsError):
        validate_title(title)


def test_cipher_and_oauth_authorization(settings):
    cipher = TokenCipher(settings)
    encrypted = cipher.encrypt({"refresh_token": "never-plaintext"})
    assert "never-plaintext" not in encrypted
    assert cipher.decrypt(encrypted)["refresh_token"] == "never-plaintext"
    with pytest.raises(ProviderFailure):
        cipher.decrypt("tampered")
    query = parse_qs(urlsplit(authorization_url(settings, "random-state", "verifier")).query)
    assert query["state"] == ["random-state"]
    assert query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) == set(SCOPES)
    assert query["redirect_uri"] == ["http://testserver/sns/youtube/callback"]


def test_http_adapter_sets_private_and_never_redirects_or_retries(settings):
    calls = []

    def handle(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer access"
        if request.method == "POST":
            import json

            body = json.loads(request.content)
            assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
            return httpx.Response(
                200,
                headers={
                    "Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test",
                },
            )
        return httpx.Response(503, text="raw-secret")

    provider = YouTubeProvider(settings, httpx.MockTransport(handle))
    upload = SimpleNamespace(title="제목", privacy="private", made_for_kids=False)
    uri = provider.initiate("access", upload, 4)
    with pytest.raises(ProviderFailure) as failure:
        provider.send("access", uri, BytesIO(b"clip"), 4)
    assert failure.value.ambiguous
    assert len(calls) == 2


@pytest.mark.parametrize(
    "uri",
    [
        "http://www.googleapis.com/upload/youtube/v3/videos?x=y",
        "https://attacker.example/upload/youtube/v3/videos?x=y",
        "https://www.googleapis.com.evil/upload/youtube/v3/videos?x=y",
        "https://user:pass@www.googleapis.com/upload/youtube/v3/videos?x=y",
        "https://www.googleapis.com/other?x=y",
    ],
)
def test_session_capability_cannot_redirect_credentials(uri):
    with pytest.raises(ProviderFailure):
        session_url(uri)


def test_oauth_missing_grant_and_probe_only_sends_empty_body(settings):
    provider = YouTubeProvider(
        settings,
        httpx.MockTransport(
            lambda req: httpx.Response(200, json={"access_token": "fake"}),
        ),
    )
    with pytest.raises(ProviderFailure):
        provider.exchange("code", "verifier")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(308, headers={"Range": "bytes=0-2"})

    provider = YouTubeProvider(settings, httpx.MockTransport(handle))
    assert (
        provider.probe("token", "https://www.googleapis.com/upload/youtube/v3/videos?x=y", 4)
        is None
    )
    assert len(requests) == 1 and requests[0].content == b""
    assert requests[0].headers["Content-Range"] == "bytes */4"


def test_session_csrf_origin_and_disabled_defaults(settings, monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[api.repository] = lambda: SimpleNamespace(accounts=lambda owner: [])
    try:
        with TestClient(app) as client:
            assert client.get("/sns/accounts").status_code == 401
            session = client.get("/sns/session")
            csrf = session.json()["csrf"]
            assert "HttpOnly" in session.headers["set-cookie"]
            assert session.headers["cache-control"] == "no-store"
            assert client.get("/sns/accounts").json() == []
            assert client.post("/sns/youtube/connect").status_code == 403
            assert (
                client.post(
                    "/sns/youtube/connect",
                    headers={
                        "Origin": "https://evil.example",
                        "X-SNS-CSRF": csrf,
                    },
                ).status_code
                == 403
            )
            assert client.get("/sns/session", headers={"Host": "evil.example"}).status_code == 403
            monkeypatch.delenv("ENABLE_SNS_UPLOAD", raising=False)
            assert Settings(_env_file=None).enable_sns_upload is False
    finally:
        app.dependency_overrides.clear()


def test_confirm_requires_exact_and_explicit_input(settings, monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    repo = WorkerRepository(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[api.repository] = lambda: repo
    app.dependency_overrides[api.publisher] = lambda: lambda *a: pytest.fail("dispatched")
    try:
        with TestClient(app) as client:
            csrf = client.get("/sns/session").json()["csrf"]
            for flag in (False, 1, "true", None):
                response = client.post(
                    f"/sns/uploads/{repo.upload.id}/confirm",
                    json={
                        "confirmed": flag,
                        "approval": approval_values(repo.upload),
                    },
                    headers={"X-SNS-CSRF": csrf},
                )
                assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_oauth_and_capability_logs_are_redacted():
    record = logging.LogRecord(
        "uvicorn.access",
        20,
        "",
        0,
        "%s %s %s %s %s",
        (
            "client",
            "GET",
            "/sns/youtube/callback?code=secret&state=secret",
            "1.1",
            303,
        ),
        None,
    )
    assert SnsAccessFilter().filter(record)
    assert "secret" not in record.getMessage()
    record.msg, record.args = "HTTP Request: https://www.googleapis.com/upload?upload_id=secret", ()
    assert not GoogleHttpFilter().filter(record)


def test_real_oauth_adapter_exchanges_code_and_refreshes_without_browser_tokens(settings):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == "/token":
            fields = parse_qs(request.content.decode())
            assert fields["client_id"] == ["fake-client"]
            assert fields["client_secret"] == ["fake-secret"]
            if fields["grant_type"] == ["authorization_code"]:
                assert fields["code_verifier"] == ["pkce-verifier"]
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ephemeral-access",
                        "refresh_token": "stored-refresh",
                        "scope": " ".join(SCOPES),
                    },
                )
            assert fields["refresh_token"] == ["stored-refresh"]
            return httpx.Response(200, json={"access_token": "new-access"})
        assert request.url.params["mine"] == "true"
        assert request.headers["Authorization"] == "Bearer ephemeral-access"
        return httpx.Response(
            200, json={"items": [{"id": "channel-1", "snippet": {"title": "채널"}}]}
        )

    provider = YouTubeProvider(settings, httpx.MockTransport(handle))
    credentials, channel = provider.exchange("code", "pkce-verifier")
    assert credentials == {"refresh_token": "stored-refresh"}
    assert channel == {"id": "channel-1", "title": "채널"}
    assert provider.access_token(credentials) == "new-access"
    assert len(requests) == 3


def test_changed_provider_channel_blocks_upload_before_remote_write(settings):
    repo, provider = WorkerRepository(settings), FakeProvider()
    provider.channel = lambda token: {"id": "another-channel"}
    process_upload(repo.upload.id, repo, settings, provider)
    assert provider.calls == ["token"]
    assert repo.upload.status == "failed"
    assert repo.upload.error_code == "ACCOUNT_CHANGED"


@pytest.mark.parametrize(
    "code,expected",
    [("CHANNEL_UNAVAILABLE", "CHANNEL_UNAVAILABLE"), ("raw-sensitive-error", "OAUTH_FAILED")],
)
def test_callback_diagnostics_log_only_known_codes(settings, monkeypatch, caplog, code, expected):
    def fail(*args, **kwargs):
        raise ProviderFailure(code)

    monkeypatch.setattr(api.sns, "complete_oauth", fail)
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[api.repository] = lambda: object()
    try:
        with TestClient(app, base_url="http://testserver") as client:
            client.get("/sns/session")
            response = client.get(
                "/sns/youtube/callback?code=secret-code&state=secret-state", follow_redirects=False
            )
        assert response.status_code == 303
        target = "/sns?oauth=error"
        if expected == "CHANNEL_UNAVAILABLE":
            target += "&reason=channel_unavailable"
        assert response.headers["location"] == target
        assert f"SNS OAuth callback failed: code={expected}" in caplog.text
        assert "secret-code" not in caplog.text
        assert "secret-state" not in caplog.text
        assert "raw-sensitive-error" not in caplog.text
    finally:
        app.dependency_overrides.clear()
