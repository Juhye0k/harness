"""Create the receipt and analysis atomically, then let the ordinary publisher run once."""

import hashlib
import json
from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.jobs import JobError
from app.models import AnalysisJob, AnalysisRequestReceipt, Asset, utcnow
from app.services.access import current_user


def owner_key():
    user = current_user.get()
    return str(user) if user else "local-development"


def input_hash(values):
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def resolve(session, receipt, digest=None):
    if receipt.expires_at <= utcnow() or receipt.analysis_id is None:
        raise JobError("REQUEST_EXPIRED", "접수가 만료됐거나 자료가 삭제됐습니다.", 410)
    if digest is not None and receipt.payload_hash != digest:
        raise JobError("REQUEST_CONFLICT", "같은 요청 번호에 다른 입력을 사용할 수 없습니다.", 409)
    job = session.get(AnalysisJob, receipt.analysis_id)
    asset = session.get(Asset, job.asset_id) if job else None
    if not asset or asset.deleted_at or (asset.expires_at and asset.expires_at <= utcnow()):
        raise JobError("RESOURCE_GONE", "만료되었거나 삭제 중인 자료입니다.", 410)
    return job


def lookup(repo, request_id, digest=None):
    with Session(repo.engine) as session:
        receipt = session.get(AnalysisRequestReceipt, (owner_key(), request_id))
        if receipt is None:
            return None
        job = resolve(session, receipt, digest)
        session.expunge(job)
        return job


def create_once(repo, request_id, digest, url, asset_id, genre, purpose, config_factory):
    with Session(repo.engine, expire_on_commit=False) as session, session.begin():
        # ON CONFLICT waits for a concurrent insert's commit. An aborted transaction
        # leaves neither a receipt nor a partly created analysis/asset behind.
        owner = owner_key()
        inserted = session.scalar(
            insert(AnalysisRequestReceipt)
            .values(
                owner_key=owner,
                request_id=request_id,
                payload_hash=digest,
                created_at=utcnow(),
                expires_at=utcnow() + timedelta(days=7),
            )
            .on_conflict_do_nothing()
            .returning(AnalysisRequestReceipt.request_id)
        )
        receipt = session.get(AnalysisRequestReceipt, (owner, request_id))
        if inserted is None:
            return resolve(session, receipt, digest), False
        config = config_factory()  # Local validation only; never a provider call.
        job = repo.create_in_session(session, url, asset_id, genre, purpose, config)
        receipt.analysis_id = job.id
        session.flush()
        return job, True
