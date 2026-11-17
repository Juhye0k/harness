from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.api.auth import verify_google
from app.models import utcnow


@pytest.mark.parametrize("fault", ["nonce", "signature", "audience", "expired", "reauth"])
def test_google_verification_rejects_bad_claims(monkeypatch, fault):
    import google.auth.transport.requests
    import google.oauth2.id_token

    from app.config import get_settings

    settings = get_settings().model_copy(update={"google_login_client_id": "expected-client"})
    monkeypatch.setattr("app.api.auth.get_settings", lambda: settings)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"id_token": "test-token"})
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "app.api.auth.httpx.Client", lambda **kwargs: real_client(transport=transport)
    )
    monkeypatch.setattr(google.auth.transport.requests, "Request", lambda: lambda *a, **k: None)

    def verify(token, request, audience):
        assert token == "test-token" and audience == "expected-client"
        if fault in {"signature", "audience", "expired"}:
            raise ValueError(fault)
        return {
            "nonce": "wrong" if fault == "nonce" else "expected",
            "auth_time": (utcnow() - timedelta(minutes=6)).timestamp(),
        }

    monkeypatch.setattr(google.oauth2.id_token, "verify_oauth2_token", verify)
    login = SimpleNamespace(
        verifier="verifier", nonce="expected", reauth_user="user" if fault == "reauth" else None
    )
    with pytest.raises(ValueError):
        verify_google("code", login)
