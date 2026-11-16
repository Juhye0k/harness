"""PostgreSQL owns confirmation, deduplication and one-shot dispatch/claim state."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db import get_engine
from app.domain.sns import SnsError, approval_values
from app.models import SnsAccount, SnsOAuthState, SnsUpload, VideoJob, utcnow


class SnsRepository:
    def __init__(self, engine=None):
        self.engine = engine if engine is not None else get_engine()

    def save_state(self, state_hash, owner, verifier):
        with Session(self.engine) as session, session.begin():
            session.execute(delete(SnsOAuthState).where(SnsOAuthState.expires_at < utcnow()))
            session.add(
                SnsOAuthState(
                    state_hash=state_hash,
                    owner=owner,
                    verifier=verifier,
                    expires_at=utcnow() + timedelta(minutes=10),
                )
            )

    def consume_state(self, state_hash, owner):
        with Session(self.engine) as session, session.begin():
            verifier = session.scalar(
                delete(SnsOAuthState)
                .where(
                    SnsOAuthState.state_hash == state_hash,
                    SnsOAuthState.owner == owner,
                    SnsOAuthState.expires_at > utcnow(),
                )
                .returning(SnsOAuthState.verifier)
            )
            if verifier is None:
                raise SnsError("INVALID_OAUTH_STATE", "계정 연결을 처음부터 다시 시작하세요.", 400)
            return verifier

    def connect(self, owner, channel, credentials):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            account = session.scalar(
                select(SnsAccount)
                .where(
                    SnsAccount.owner == owner,
                    SnsAccount.channel_id == channel["id"],
                )
                .with_for_update()
            )
            if account is None:
                account = SnsAccount(owner=owner, channel_id=channel["id"], version=0)
                session.add(account)
            account.version += 1
            account.channel_title = channel["title"][:256]
            account.credentials, account.connected = credentials, True
            session.flush()
            return account

    def accounts(self, owner):
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(SnsAccount).where(
                        SnsAccount.owner == owner,
                        SnsAccount.connected.is_(True),
                    )
                )
            )

    @staticmethod
    def owned_account(session, account_id, owner):
        account = session.scalar(
            select(SnsAccount)
            .where(
                SnsAccount.id == account_id,
                SnsAccount.owner == owner,
            )
            .with_for_update()
        )
        if account is None:
            raise SnsError("ACCOUNT_NOT_FOUND", "연결 계정을 찾을 수 없습니다.", 404)
        return account

    def disconnect(self, account_id, owner):
        with Session(self.engine) as session, session.begin():
            account = self.owned_account(session, account_id, owner)
            account.connected, account.credentials = False, ""
            account.version += 1

    def account(self, account_id):
        with Session(self.engine) as session:
            account = session.get(SnsAccount, account_id)
            if account is None or not account.connected:
                raise SnsError("RECONNECT_REQUIRED", "YouTube 계정을 다시 연결하세요.")
            return account

    def output(self, job_id):
        with Session(self.engine) as session:
            job = session.get(VideoJob, job_id)
            if job is None or job.status != "succeeded":
                raise SnsError("OUTPUT_NOT_READY", "검증된 영상 출력이 필요합니다.")
            return job

    def prepare(self, owner, request_id, account_id, job_id, version, size, title, privacy, kids):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            account = self.owned_account(session, account_id, owner)
            existing = session.scalar(
                select(SnsUpload).where(
                    SnsUpload.owner == owner,
                    SnsUpload.request_id == request_id,
                )
            )
            values = dict(
                account_id=str(account_id),
                account_version=account.version,
                job_id=str(job_id),
                output_version=version,
                title=title,
                privacy=privacy,
                made_for_kids=kids,
            )
            if existing:
                if approval_values(existing) != values:
                    raise SnsError("REQUEST_CONFLICT", "같은 요청 번호의 내용이 변경됐습니다.")
                return existing
            if not account.connected:
                raise SnsError("RECONNECT_REQUIRED", "YouTube 계정을 다시 연결하세요.")
            upload = SnsUpload(
                owner=owner,
                request_id=request_id,
                account_id=account.id,
                account_version=account.version,
                channel_id=account.channel_id,
                channel_title=account.channel_title,
                job_id=job_id,
                output_version=version,
                output_size=size,
                title=title,
                privacy=privacy,
                made_for_kids=kids,
                expires_at=utcnow() + timedelta(minutes=15),
            )
            session.add(upload)
            session.flush()
            return upload

    def get(self, upload_id, owner=None):
        with Session(self.engine) as session:
            upload = session.get(SnsUpload, upload_id)
            if upload is None or (owner is not None and upload.owner != owner):
                raise SnsError("UPLOAD_NOT_FOUND", "업로드 작업을 찾을 수 없습니다.", 404)
            return upload

    def confirm(self, upload_id, owner, values, publish):
        initial = self.get(upload_id, owner)
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            account = self.owned_account(session, initial.account_id, owner)
            upload = session.scalar(
                select(SnsUpload)
                .where(
                    SnsUpload.id == upload_id,
                )
                .with_for_update()
            )
            if approval_values(upload) != values:
                raise SnsError("APPROVAL_MISMATCH", "확인한 업로드 설정이 변경됐습니다.")
            if upload.status != "draft":
                return upload
            if upload.expires_at <= utcnow():
                raise SnsError(
                    "APPROVAL_EXPIRED", "확인 시간이 지났습니다. 미리보기를 다시 만드세요."
                )
            if not account.connected or account.version != upload.account_version:
                raise SnsError("ACCOUNT_CHANGED", "계정 연결이 변경됐습니다. 다시 확인하세요.")
            duplicate = session.scalar(
                select(SnsUpload).where(
                    SnsUpload.account_id == upload.account_id,
                    SnsUpload.job_id == upload.job_id,
                    SnsUpload.output_version == upload.output_version,
                    SnsUpload.status != "draft",
                )
            )
            if duplicate:
                if approval_values(duplicate) != values:
                    raise SnsError("DUPLICATE_OUTPUT", "같은 계정·출력의 기존 업로드를 확인하세요.")
                return duplicate
            upload.status, upload.confirmed_at = "queued", utcnow()
            try:
                publish(upload.id, upload.task_id)
            except Exception:
                # A delivered message still waits for this lock and cannot claim failed.
                upload.status, upload.error_code = "failed", "DISPATCH_FAILED"
                upload.finished_at = utcnow()
            session.flush()
            return upload

    def claim(self, upload_id):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            upload = session.scalar(
                select(SnsUpload)
                .where(
                    SnsUpload.id == upload_id,
                )
                .with_for_update()
            )
            if upload is None or upload.status != "queued" or upload.confirmed_at is None:
                return None
            upload.status, upload.started_at = "running", utcnow()
            session.flush()
            return upload

    def record_session(self, upload_id, uri):
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                update(SnsUpload)
                .where(
                    SnsUpload.id == upload_id,
                    SnsUpload.status == "running",
                )
                .values(session_uri=uri)
            )
            return result.rowcount == 1

    def finish(self, upload_id, status, *, expected="running", **values):
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                update(SnsUpload)
                .where(
                    SnsUpload.id == upload_id,
                    SnsUpload.status == expected,
                )
                .values(status=status, finished_at=utcnow(), **values)
            )
            return result.rowcount == 1

    def mark_unknown(self, upload_id):
        # Operator must first stop the specific worker; never turn uncertainty into failure.
        return self.finish(upload_id, "unknown", error_code="INTERRUPTED")

    def request_probe(self, upload_id, owner, publish):
        with Session(self.engine) as session, session.begin():
            upload = session.scalar(
                select(SnsUpload)
                .where(
                    SnsUpload.id == upload_id,
                    SnsUpload.owner == owner,
                )
                .with_for_update()
            )
            if upload is None:
                raise SnsError("UPLOAD_NOT_FOUND", "작업을 찾을 수 없습니다.", 404)
            if upload.status != "unknown" or not upload.session_uri:
                raise SnsError("PROBE_UNAVAILABLE", "조회 가능한 미확정 전송 세션이 없습니다.")
            if upload.probe_task_id is None:
                upload.probe_task_id = uuid4()
                publish(upload.id, upload.probe_task_id)

    def claim_probe(self, upload_id, task_id):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            return session.scalar(
                update(SnsUpload)
                .where(
                    SnsUpload.id == upload_id,
                    SnsUpload.status == "unknown",
                    SnsUpload.probe_task_id == task_id,
                )
                .values(probe_task_id=None)
                .returning(SnsUpload)
            )
