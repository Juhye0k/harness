"""Google identity verification, explicit tester approval and revocable app sessions."""

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth_models import AuthSession, Identity, LoginState, User
from app.config import get_settings
from app.db import get_engine
from app.domain.jobs import JobError
from app.models import utcnow

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE = "shortform_session"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf(token):
    return hmac.new(token.encode(), b"shortform-csrf", hashlib.sha256).hexdigest()


def session_user(token, activity=False):
    with Session(get_engine()) as s, s.begin():
        row = s.get(AuthSession, digest(token))
        now = utcnow()
        if not row or row.expires_at <= now or row.last_activity + timedelta(hours=24) <= now:
            raise JobError("SESSION_REQUIRED", "로그인이 필요합니다.", 401)
        user = s.get(User, row.user_id)
        if not user or user.state != "active":
            raise JobError("SESSION_REQUIRED", "로그인이 필요합니다.", 401)
        if activity:
            row.last_activity = now
        return user.id, row.reauthenticated_at


def set_cookie(response, name, value, age):
    settings = get_settings()
    response.set_cookie(
        name,
        value,
        max_age=age,
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.auth_origin.startswith("https://"),
    )


@router.get("/google/start")
def start(request: Request, reauthenticate: bool = False):
    settings = get_settings()
    if (
        not settings.enable_auth
        or not settings.google_login_client_id
        or not settings.google_login_client_secret.get_secret_value()
    ):
        raise JobError("AUTH_NOT_CONFIGURED", "Google 로그인 설정이 필요합니다.", 503)
    user = session_user(request.cookies.get(COOKIE, ""))[0] if reauthenticate else None
    state, browser, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
    with Session(get_engine()) as s, s.begin():
        s.execute(delete(LoginState).where(LoginState.expires_at <= utcnow()))
        s.add(
            LoginState(
                state_hash=digest(state),
                browser_hash=digest(browser),
                nonce=nonce,
                verifier=verifier,
                expires_at=utcnow() + timedelta(minutes=10),
                reauth_user=user,
            )
        )
    params = dict(
        client_id=settings.google_login_client_id,
        response_type="code",
        redirect_uri=settings.auth_origin + "/auth/google/callback",
        scope="openid email",
        state=state,
        nonce=nonce,
        code_challenge_method="S256",
        code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("="),
    )
    if reauthenticate:
        params.update(prompt="login", max_age="0")
    response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))
    set_cookie(response, "shortform_login", browser, 600)
    return response


def verify_google(code, login):
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.id_token import verify_oauth2_token

    settings = get_settings()
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_login_client_id,
                "client_secret": settings.google_login_client_secret.get_secret_value(),
                "redirect_uri": settings.auth_origin + "/auth/google/callback",
                "grant_type": "authorization_code",
                "code_verifier": login.verifier,
            },
        )
        response.raise_for_status()
        token = response.json()["id_token"]
    transport = GoogleRequest()

    def timed_request(*args, **kwargs):
        kwargs["timeout"] = 10
        return transport(*args, **kwargs)

    claims = verify_oauth2_token(token, timed_request, settings.google_login_client_id)
    if not hmac.compare_digest(claims.get("nonce", ""), login.nonce):
        raise ValueError("nonce")
    if login.reauth_user and utcnow().timestamp() - claims.get("auth_time", 0) > 300:
        raise ValueError("reauthentication")
    return claims


@router.get("/google/callback")
def callback(request: Request):
    state = request.query_params.get("state", "")
    browser = request.cookies.get("shortform_login", "")
    with Session(get_engine(), expire_on_commit=False) as s, s.begin():
        login = s.scalar(
            select(LoginState).where(LoginState.state_hash == digest(state)).with_for_update()
        )
        if (
            not login
            or login.expires_at <= utcnow()
            or not hmac.compare_digest(login.browser_hash, digest(browser))
        ):
            raise JobError("INVALID_LOGIN", "로그인을 다시 시작하세요.", 400)
        s.delete(login)
    try:
        claims = verify_google(request.query_params.get("code", ""), login)
    except Exception as exc:
        raise JobError("INVALID_LOGIN", "Google 인증을 완료하지 못했습니다.", 400) from exc
    with Session(get_engine(), expire_on_commit=False) as s, s.begin():
        # One issuer spelling prevents accidental duplicate accounts.
        identity = s.scalar(
            select(Identity).where(
                Identity.issuer == "https://accounts.google.com", Identity.subject == claims["sub"]
            )
        )
        if identity is None:
            user = User()
            s.add(user)
            s.flush()
            s.add(
                Identity(
                    user_id=user.id, issuer="https://accounts.google.com", subject=claims["sub"]
                )
            )
        else:
            user = s.scalar(select(User).where(User.id == identity.user_id).with_for_update())
        if login.reauth_user and user.id != login.reauth_user:
            raise JobError("WRONG_ACCOUNT", "같은 Google 계정으로 재인증하세요.", 403)
        if user.state != "active":
            response = RedirectResponse("/login?pending=" + str(user.id), status_code=303)
        else:
            token = secrets.token_urlsafe(32)
            s.execute(
                delete(AuthSession).where(
                    AuthSession.token_hash == digest(request.cookies.get(COOKIE, ""))
                )
            )
            s.add(
                AuthSession(
                    token_hash=digest(token),
                    user_id=user.id,
                    expires_at=utcnow() + timedelta(days=7),
                    reauthenticated_at=utcnow() if login.reauth_user else None,
                )
            )
            response = RedirectResponse("/my-data", status_code=303)
            set_cookie(response, COOKIE, token, 7 * 86400)
    response.delete_cookie("shortform_login", path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/me")
def me(request: Request):
    if not get_settings().enable_auth:
        return {"enabled": False}
    token = request.cookies.get(COOKIE, "")
    user, reauth = session_user(token)
    return {
        "enabled": True,
        "user_id": str(user),
        "csrf": csrf(token),
        "reauthenticated_at": reauth,
    }


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    with Session(get_engine()) as s, s.begin():
        s.execute(
            delete(AuthSession).where(
                AuthSession.token_hash == digest(request.cookies.get(COOKIE, ""))
            )
        )
    response.delete_cookie(COOKIE, path="/")
