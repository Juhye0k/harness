"""Short DB transactions coordinate requests, workers and deletion."""

from contextvars import ContextVar
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth_models import ResourceUse, User
from app.db import get_engine
from app.domain.jobs import JobError
from app.models import AnalysisJob, Asset, VideoJob, utcnow

current_user = ContextVar("current_user", default=None)


def owned(session, kind, resource_id, user_id):
    model = Asset if kind == "asset" else VideoJob
    row = session.scalar(select(model).where(model.id == resource_id, model.user_id == user_id))
    if row is None:
        raise JobError("NOT_FOUND", "자료를 찾을 수 없습니다.", 404)
    if row.deleted_at or row.expires_at <= utcnow():
        raise JobError("RESOURCE_GONE", "만료되었거나 삭제 중인 자료입니다.", 410)
    return row


def root_for(session, kind, resource_id):
    if kind == "analysis":
        row = session.get(AnalysisJob, resource_id)
        return ("asset", row.asset_id) if row else ("asset", resource_id)
    if kind == "job":
        row = session.get(VideoJob, resource_id)
        if row and row.asset_id:
            return "asset", row.asset_id
    return kind, resource_id


def acquire(user_id, resources, engine=None):
    with Session(engine or get_engine()) as s, s.begin():
        user = s.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or user.state != "active":
            raise JobError("SESSION_REQUIRED", "로그인이 필요합니다.", 401)
        uses = []
        use = ResourceUse(user_id=user_id, kind="user", resource_id=user_id)
        s.add(use)
        s.flush()
        uses.append(use.id)
        for kind, resource_id in set(resources):
            # Check the requested job too: an individually deleted output cannot be read.
            if kind == "job":
                owned(s, kind, resource_id, user_id)
            kind, resource_id = root_for(s, kind, resource_id)
            owned(s, kind, resource_id, user_id)
            use = ResourceUse(user_id=user_id, kind=kind, resource_id=resource_id)
            s.add(use)
            s.flush()
            uses.append(use.id)
        return uses


def release(uses, engine=None):
    if uses:
        with Session(engine or get_engine()) as s, s.begin():
            s.execute(delete(ResourceUse).where(ResourceUse.id.in_(uses)))


def ownership_values():
    user = current_user.get()
    return {
        "user_id": user,
        "legacy": user is None,
        "expires_at": utcnow() + timedelta(days=7) if user else None,
    }


def worker_guard(kind, repository_parameter):
    from functools import wraps
    from inspect import signature

    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            from app.config import get_settings
            from app.models import SnsUpload

            if not get_settings().enable_auth:
                return function(*args, **kwargs)
            bound = signature(function).bind(*args, **kwargs).arguments
            repo = bound[repository_parameter]
            resource_id = next(iter(bound.values()))
            with Session(repo.engine) as s:
                if kind == "sns":
                    upload = s.get(SnsUpload, resource_id)
                    if not upload:
                        return
                    resource_id = upload.job_id
                actual_kind = "job" if kind == "sns" else kind
                root_kind, root_id = root_for(s, actual_kind, resource_id)
                row = s.get(Asset if root_kind == "asset" else VideoJob, root_id)
                if not row or not row.user_id:
                    return
                user = row.user_id
                if kind == "sns" and upload.owner != str(user):
                    return
            try:
                uses = acquire(user, [(actual_kind, resource_id)], repo.engine)
            except JobError:
                return
            try:
                return function(*args, **kwargs)
            finally:
                # A killed process never executes this; its use record blocks cleanup.
                release(uses, repo.engine)

        return run

    return decorate
