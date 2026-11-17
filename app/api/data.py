"""Owned listings, deletion previews and durable deletion requests."""

import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.auth import COOKIE, digest, session_user
from app.auth_models import AuthSession, Deletion, ResourceUse, User
from app.db import get_engine
from app.domain.jobs import JobError
from app.models import AnalysisJob, Asset, SnsUpload, VideoJob, utcnow
from app.services.access import current_user, owned

router = APIRouter(tags=["user data"])


def active_jobs(s, kind, resource_id):
    if kind == "user":
        assets = select(Asset.id).where(Asset.user_id == resource_id)
        jobs = select(VideoJob.id).where(VideoJob.user_id == resource_id)
    elif kind == "asset":
        assets = select(Asset.id).where(Asset.id == resource_id)
        jobs = select(VideoJob.id).where(VideoJob.asset_id == resource_id)
    else:
        assets = select(Asset.id).where(Asset.id.is_(None))
        jobs = select(VideoJob.id).where(VideoJob.id == resource_id)
    return bool(
        s.scalar(
            select(VideoJob.id)
            .where(VideoJob.id.in_(jobs), VideoJob.status.in_(("pending", "queued", "running")))
            .limit(1)
        )
        or s.scalar(
            select(AnalysisJob.id)
            .where(
                AnalysisJob.asset_id.in_(assets),
                AnalysisJob.status.in_(("pending", "queued", "running")),
            )
            .limit(1)
        )
        or s.scalar(
            select(SnsUpload.id)
            .where(
                SnsUpload.job_id.in_(jobs), SnsUpload.status.in_(("queued", "running", "unknown"))
            )
            .limit(1)
        )
    )


def preview(s, kind, resource_id, user):
    row = owned(s, kind, resource_id, user)
    outputs = (
        list(s.scalars(select(VideoJob.id).where(VideoJob.asset_id == resource_id)))
        if kind == "asset"
        else [resource_id]
    )
    return {
        "id": str(row.id),
        "kind": kind,
        "outputs": [str(x) for x in outputs],
        "includes_original": kind == "asset",
        "busy": active_jobs(s, kind, resource_id),
        "deletes_youtube_video": False,
    }


def listing(model, limit, offset):
    user = current_user.get()
    if user is None:
        raise JobError("SESSION_REQUIRED", "로그인이 필요합니다.", 401)
    with Session(get_engine()) as s:
        rows = s.scalars(
            select(model)
            .where(model.user_id == user)
            .order_by(model.created_at.desc(), model.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            {
                "id": str(r.id),
                "expires_at": r.expires_at,
                "created_at": r.created_at,
                "deleting": bool(r.deleted_at),
                "status": getattr(r, "status", r.state if isinstance(r, Asset) else None),
            }
            for r in rows
        ]


@router.get("/assets")
def assets(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return listing(Asset, limit, offset)


@router.get("/jobs")
def jobs(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return listing(VideoJob, limit, offset)


@router.get("/assets/{resource_id}/deletion-preview")
def asset_preview(resource_id: UUID):
    with Session(get_engine()) as s:
        return preview(s, "asset", resource_id, current_user.get())


@router.get("/jobs/{resource_id}/deletion-preview")
def job_preview(resource_id: UUID):
    with Session(get_engine()) as s:
        return preview(s, "job", resource_id, current_user.get())


def request_delete(kind, resource_id):
    user = current_user.get()
    with Session(get_engine()) as s, s.begin():
        s.scalar(select(User).where(User.id == user).with_for_update())
        existing = s.scalar(
            select(Deletion).where(
                Deletion.kind == kind, Deletion.resource_id == resource_id, Deletion.user_id == user
            )
        )
        if existing:
            return {"deletion_id": str(existing.id), "status_url": f"/deletions/{existing.id}"}
        row = owned(s, kind, resource_id, user)
        uses = s.scalar(select(ResourceUse.id).where(ResourceUse.user_id == user).limit(1))
        if uses or active_jobs(s, kind, resource_id):
            raise JobError("RESOURCE_BUSY", "처리·재생이 끝난 뒤 삭제하세요.", 409)
        row.deleted_at = utcnow()
        deletion = Deletion(user_id=user, kind=kind, resource_id=resource_id)
        s.add(deletion)
        s.flush()
        return {"deletion_id": str(deletion.id), "status_url": f"/deletions/{deletion.id}"}


@router.delete("/assets/{resource_id}", status_code=202)
def delete_asset(resource_id: UUID):
    return request_delete("asset", resource_id)


@router.delete("/jobs/{resource_id}", status_code=202)
def delete_job(resource_id: UUID):
    return request_delete("job", resource_id)


@router.get("/deletions/{deletion_id}")
def deletion_status(deletion_id: UUID):
    with Session(get_engine()) as s:
        row = s.scalar(
            select(Deletion).where(
                Deletion.id == deletion_id, Deletion.user_id == current_user.get()
            )
        )
        if not row:
            raise JobError("NOT_FOUND", "삭제 작업을 찾을 수 없습니다.", 404)
        return {"id": str(row.id), "state": row.state, "error": row.error}


@router.delete("/auth/me", status_code=202)
def leave(request: Request):
    user, reauth = session_user(request.cookies.get(COOKIE, ""))
    if not reauth or reauth + timedelta(minutes=5) < utcnow():
        raise JobError("REAUTH_REQUIRED", "Google 재인증이 필요합니다.", 403)
    token = secrets.token_urlsafe(32)
    with Session(get_engine()) as s, s.begin():
        row = s.scalar(select(User).where(User.id == user).with_for_update())
        row.state = "deleting"
        s.execute(delete(AuthSession).where(AuthSession.user_id == user))
        item = Deletion(user_id=user, kind="user", resource_id=user, token_hash=digest(token))
        s.add(item)
        s.flush()
        return {
            "deletion_id": str(item.id),
            "status_url": f"/deletion-status/{item.id}",
            "token": token,
        }


@router.get("/deletion-status/{deletion_id}")
def detached_status(deletion_id: UUID, request: Request):
    with Session(get_engine()) as s:
        row = s.scalar(
            select(Deletion).where(
                Deletion.id == deletion_id,
                Deletion.token_hash == digest(request.headers.get("x-deletion-token", "")),
            )
        )
        if not row or row.created_at + timedelta(days=30) < utcnow():
            raise JobError("NOT_FOUND", "삭제 작업을 찾을 수 없습니다.", 404)
        return {"state": row.state, "error": row.error}
