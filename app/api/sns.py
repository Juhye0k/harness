"""Browser-session owned, same-origin local YouTube API; credentials never leave server."""

import hmac
import logging
import re
import secrets
from collections.abc import Callable
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.adapters.sns_repository import SnsRepository
from app.adapters.youtube_upload import ProviderFailure
from app.config import get_settings
from app.domain.sns import SnsError, digest
from app.services import sns

router = APIRouter(prefix="/sns", tags=["YouTube uploads"])
COOKIE = "shortform_sns"
logger = logging.getLogger(__name__)
OAUTH_FAILURE_CODES = frozenset(
    {
        "INVALID_OAUTH_STATE",
        "OAUTH_DENIED",
        "SNS_DISABLED",
        "SNS_NOT_CONFIGURED",
        "RECONNECT_REQUIRED",
        "CHANNEL_UNAVAILABLE",
        "PROVIDER_REJECTED",
        "PROVIDER_UNREACHABLE",
        "INVALID_PROVIDER_RESPONSE",
        "CREDENTIALS_UNAVAILABLE",
    }
)


def repository():
    return SnsRepository()


def publisher():
    from app.adapters.job_publisher import publish_sns_upload

    return publish_sns_upload


def probe_publisher():
    from app.adapters.job_publisher import publish_sns_probe

    return publish_sns_probe


def check_origin(request):
    settings = get_settings()
    origin = settings.sns_origin
    host = urlsplit(origin).hostname
    local = host in {"localhost", "127.0.0.1", "::1"}
    test = settings.app_env == "test" and host in {"api", "testserver"}
    if not (local or test) or str(request.base_url).rstrip("/") != origin:
        raise SnsError("LOCAL_ORIGIN_REQUIRED", "설정한 로컬 주소에서 접속하세요.", 403)
    if request.headers.get("origin") not in (None, origin):
        raise SnsError("CROSS_ORIGIN_DENIED", "같은 앱 화면에서 요청하세요.", 403)


def session_token(request):
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise SnsError("SESSION_REQUIRED", "SNS 화면을 다시 열어 주세요.", 401)
    return token


def owner(request: Request):
    check_origin(request)
    token = session_token(request)
    if request.method not in {"GET", "HEAD"}:
        supplied = request.headers.get("x-sns-csrf", "")
        if not hmac.compare_digest(supplied, digest(token + ":csrf")):
            raise SnsError("CSRF_DENIED", "SNS 화면에서 다시 요청하세요.", 403)
    return digest(token)


Owner = Annotated[str, Depends(owner)]
Repo = Annotated[SnsRepository, Depends(repository)]


@router.get("/session")
def session(request: Request, response: Response):
    check_origin(request)
    try:
        token = session_token(request)
    except SnsError:
        token = secrets.token_urlsafe(32)
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=7 * 24 * 3600,
        path="/sns",
    )
    return {"csrf": digest(token + ":csrf"), "enabled": get_settings().enable_sns_upload}


@router.post("/youtube/connect")
def connect(repo: Repo, user: Owner):
    return {"authorization_url": sns.start_oauth(repo, get_settings(), user)}


@router.get("/youtube/callback", include_in_schema=False)
def callback(request: Request, repo: Repo, user: Owner):
    # Never reflect provider errors, codes or tokens. State is consumed even on denial.
    try:
        state = request.query_params.get("state", "")
        code = request.query_params.get("code", "")
        if len(state) > 128 or len(code) > 4096:
            raise SnsError("INVALID_OAUTH_STATE", "계정 연결을 다시 시작하세요.", 400)
        sns.complete_oauth(repo, get_settings(), user, state, code)
    except (SnsError, ProviderFailure) as exc:
        code = exc.code if exc.code in OAUTH_FAILURE_CODES else "OAUTH_FAILED"
        logger.warning("SNS OAuth callback failed: code=%s", code)
        target = "/sns?oauth=error"
        if code == "CHANNEL_UNAVAILABLE":
            target += "&reason=channel_unavailable"
        return RedirectResponse(target, status_code=303)
    return RedirectResponse("/sns?oauth=connected", status_code=303)


@router.get("/accounts")
def accounts(repo: Repo, user: Owner):
    return [
        {
            "account_id": str(a.id),
            "channel_id": a.channel_id,
            "title": a.channel_title,
            "version": a.version,
        }
        for a in repo.accounts(user)
    ]


@router.delete("/accounts/{account_id}", status_code=204)
def disconnect(account_id: UUID, repo: Repo, user: Owner):
    repo.disconnect(account_id, user)


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    account_id: UUID
    job_id: UUID
    title: str = Field(min_length=1, max_length=100)
    privacy: Literal["private", "unlisted", "public"] = "private"
    made_for_kids: StrictBool


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    account_version: int = Field(ge=1)
    job_id: UUID
    output_version: str = Field(pattern="^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=100)
    privacy: Literal["private", "unlisted", "public"]
    made_for_kids: StrictBool


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: StrictBool
    approval: Approval


@router.post("/uploads", status_code=201)
def prepare(body: DraftRequest, repo: Repo, user: Owner):
    return sns.public_upload(sns.prepare(repo, get_settings(), user, body))


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: UUID, repo: Repo, user: Owner):
    return sns.public_upload(repo.get(upload_id, user))


@router.post("/uploads/{upload_id}/confirm", status_code=202)
def confirm(
    upload_id: UUID,
    body: ConfirmRequest,
    repo: Repo,
    user: Owner,
    publish: Annotated[Callable, Depends(publisher)],
):
    if body.confirmed is not True:
        raise SnsError("CONFIRMATION_REQUIRED", "명시적인 업로드 확인이 필요합니다.", 422)
    upload = sns.confirm(
        repo,
        get_settings(),
        user,
        upload_id,
        body.approval.model_dump(mode="json"),
        publish,
    )
    return sns.public_upload(upload)


@router.post("/uploads/{upload_id}/probe", status_code=202)
def probe(
    upload_id: UUID,
    repo: Repo,
    user: Owner,
    publish: Annotated[Callable, Depends(probe_publisher)],
):
    sns.enabled(get_settings())
    repo.request_probe(upload_id, user, publish)
    return sns.public_upload(repo.get(upload_id, user))
