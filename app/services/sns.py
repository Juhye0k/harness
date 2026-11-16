"""Explicit approval precedes one-shot upload. Uncertainty never triggers re-upload."""

import hashlib
import logging
import secrets
import tempfile
from uuid import UUID

from app.adapters.youtube_upload import (
    ProviderFailure,
    TokenCipher,
    YouTubeProvider,
    authorization_url,
)
from app.domain.jobs import output_file
from app.domain.sns import SnsError, approval_values, digest, output_version, validate_title

logger = logging.getLogger(__name__)


def enabled(settings):
    if not settings.enable_sns_upload:
        raise SnsError("SNS_DISABLED", "SNS 업로드가 비활성화돼 있습니다.", 503)
    if not settings.youtube_client_id or not settings.youtube_client_secret.get_secret_value():
        raise SnsError("SNS_NOT_CONFIGURED", "YouTube OAuth 설정을 확인하세요.", 503)
    return TokenCipher(settings)


def start_oauth(repo, settings, owner):
    cipher = enabled(settings)
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    repo.save_state(digest(state), owner, cipher.encrypt(verifier))
    return authorization_url(settings, state, verifier)


def complete_oauth(repo, settings, owner, state, code, provider=None):
    cipher = enabled(settings)
    verifier = cipher.decrypt(repo.consume_state(digest(state), owner))
    if not code:
        raise SnsError("OAUTH_DENIED", "계정 연결이 취소되거나 거절됐습니다.", 400)
    provider = provider or YouTubeProvider(settings)
    credentials, channel = provider.exchange(code, verifier)
    return repo.connect(owner, channel, cipher.encrypt(credentials))


def prepare(repo, settings, owner, body):
    enabled(settings)
    validate_title(body.title)
    job = repo.output(body.job_id)
    path = output_file(settings.video_data_dir, job.output_path)
    return repo.prepare(
        owner,
        body.request_id,
        body.account_id,
        body.job_id,
        output_version(path),
        path.stat().st_size,
        body.title,
        body.privacy,
        body.made_for_kids,
    )


def confirm(repo, settings, owner, upload_id, values, publish):
    enabled(settings)
    upload = repo.get(upload_id, owner)
    if upload.status == "draft":
        path = output_file(settings.video_data_dir, repo.output(upload.job_id).output_path)
        if output_version(path) != upload.output_version:
            raise SnsError("OUTPUT_CHANGED", "출력 버전이 변경됐습니다. 다시 확인하세요.")
    return repo.confirm(upload_id, owner, values, publish)


def public_upload(upload):
    return {
        "upload_id": str(upload.id),
        "status": upload.status,
        "approval": approval_values(upload),
        "account": {"channel_id": upload.channel_id, "title": upload.channel_title},
        "expires_at": upload.expires_at,
        "confirmed_at": upload.confirmed_at,
        "error_code": upload.error_code,
        "video_url": f"https://www.youtube.com/watch?v={upload.remote_id}"
        if upload.remote_id
        else None,
        "can_probe": upload.status == "unknown" and bool(upload.session_uri),
        "preview_url": f"/jobs/{upload.job_id}/download",
    }


def process_upload(upload_id: UUID, repo, settings, provider=None):
    upload = repo.claim(upload_id)
    if upload is None:
        return
    provider = provider or YouTubeProvider(settings)
    remote_started = False
    try:
        cipher = enabled(settings)
        account = repo.account(upload.account_id)
        if account.version != upload.account_version or account.channel_id != upload.channel_id:
            raise SnsError("ACCOUNT_CHANGED", "계정 연결이 변경됐습니다.")
        path = output_file(settings.video_data_dir, repo.output(upload.job_id).output_path)
        # Freeze the approved bytes before any network call. Sending uses this open snapshot.
        with tempfile.TemporaryFile() as snapshot, path.open("rb") as source:
            remaining = upload.output_size
            while remaining:
                chunk = source.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise SnsError("OUTPUT_CHANGED", "출력이 변경됐습니다.")
                snapshot.write(chunk)
                remaining -= len(chunk)
            if source.read(1):
                raise SnsError("OUTPUT_CHANGED", "출력이 변경됐습니다.")
            snapshot.seek(0)
            if hashlib.file_digest(snapshot, "sha256").hexdigest() != upload.output_version:
                raise SnsError("OUTPUT_CHANGED", "출력이 변경됐습니다.")
            snapshot.seek(0)
            token = provider.access_token(cipher.decrypt(account.credentials))
            if provider.channel(token)["id"] != upload.channel_id:
                raise SnsError("ACCOUNT_CHANGED", "업로드 계정을 확인할 수 없습니다.")
            remote_started = True
            uri = provider.initiate(token, upload, upload.output_size)
            if not repo.record_session(upload.id, cipher.encrypt(uri)):
                return  # Operator changed state before media transfer; never continue.
            remote_id = provider.send(token, uri, snapshot, upload.output_size)
        repo.finish(upload.id, "succeeded", remote_id=remote_id, error_code=None)
    except Exception as exc:
        ambiguous = remote_started
        code = "UPLOAD_UNCONFIRMED" if ambiguous else "UPLOAD_FAILED"
        if isinstance(exc, ProviderFailure):
            ambiguous = remote_started and exc.ambiguous
            code = exc.code
        elif isinstance(exc, SnsError):
            code = exc.code
        logger.warning("SNS upload ended: upload_id=%s code=%s", upload.id, code)
        # DB failure can leave running; operator marks unknown after stopping the worker.
        repo.finish(upload.id, "unknown" if ambiguous else "failed", error_code=code)


def probe_upload(upload_id, task_id, repo, settings, provider=None):
    upload = repo.claim_probe(upload_id, task_id)
    if upload is None:
        return
    provider = provider or YouTubeProvider(settings)
    try:
        cipher = enabled(settings)
        account = repo.account(upload.account_id)
        token = provider.access_token(cipher.decrypt(account.credentials))
        if provider.channel(token)["id"] != upload.channel_id:
            return
        remote_id = provider.probe(token, cipher.decrypt(upload.session_uri), upload.output_size)
        if remote_id:
            repo.finish(
                upload.id, "succeeded", expected="unknown", remote_id=remote_id, error_code=None
            )
    except Exception:
        logger.warning("SNS session status unconfirmed: upload_id=%s", upload.id)
