"""Bounded filesystem cleanup. Durable busy records never expire automatically."""

import argparse
import shutil
import time
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.data import active_jobs
from app.auth_models import AuthSession, Deletion, Identity, LoginState, ResourceUse, User
from app.config import get_settings
from app.db import get_engine
from app.models import (
    AnalysisJob,
    Asset,
    HighlightCandidate,
    ProviderCall,
    SnsAccount,
    SnsOAuthState,
    SnsUpload,
    Transcript,
    TranscriptReview,
    VideoJob,
    utcnow,
)


def remove_tree(root, relative):
    root = root.resolve()
    raw = root / relative
    resolved = raw.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError("outside data root")
    for path in [raw, *raw.parents]:
        if path == root:
            break
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("linked directory")
    if raw.exists():
        for path in raw.rglob("*"):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("linked file")
        shutil.rmtree(raw)


def scrub(s, item, root):
    user = item.user_id
    asset_filter = Asset.user_id == user if item.kind == "user" else Asset.id == item.resource_id
    assets = list(s.scalars(select(Asset).where(asset_filter))) if item.kind != "job" else []
    asset_ids = [a.id for a in assets]
    job_filter = (
        VideoJob.user_id == user
        if item.kind == "user"
        else VideoJob.asset_id.in_(asset_ids)
        if item.kind == "asset"
        else VideoJob.id == item.resource_id
    )
    jobs = list(s.scalars(select(VideoJob).where(job_filter)))
    job_ids = [j.id for j in jobs]
    analyses = list(s.scalars(select(AnalysisJob.id).where(AnalysisJob.asset_id.in_(asset_ids))))
    # Persisted directory layout, never caller-supplied paths.
    for job in jobs:
        remove_tree(root, str(job.id))
    for asset in assets:
        remove_tree(root, "assets/" + str(asset.id))
    for analysis in analyses:
        remove_tree(root, "verification/" + str(analysis))
    s.execute(delete(SnsUpload).where(SnsUpload.job_id.in_(job_ids)))
    for job in jobs:
        job.source_url, job.output_path, job.result = "", None, None
        job.error_message, job.operator_reason = None, None
        job.deleted_at = utcnow()
    if item.kind in {"asset", "user"}:
        # Flush FK references from export jobs before deleting candidates.
        for job in jobs:
            job.candidate_id = None
        s.flush()
        for model in (TranscriptReview, ProviderCall, HighlightCandidate):
            s.execute(delete(model).where(model.analysis_id.in_(analyses)))
        s.execute(delete(AnalysisJob).where(AnalysisJob.id.in_(analyses)))
        s.execute(delete(Transcript).where(Transcript.asset_id.in_(asset_ids)))
        for asset in assets:
            asset.source_url, asset.path, asset.sha256 = "", None, None
            asset.deleted_at = utcnow()
    if item.kind == "user":
        # Old anonymous SNS credentials are not silently adopted or deleted.
        s.execute(delete(SnsOAuthState).where(SnsOAuthState.owner == str(user)))
        s.execute(delete(SnsUpload).where(SnsUpload.owner == str(user)))
        s.execute(delete(SnsAccount).where(SnsAccount.owner == str(user)))
        s.execute(delete(AuthSession).where(AuthSession.user_id == user))
        s.execute(delete(LoginState).where(LoginState.reauth_user == user))
        s.execute(delete(Identity).where(Identity.user_id == user))
        s.get(User, user).state = "deleted"


def sweep(engine=None, root=None, dry_run=False):
    engine = engine or get_engine()
    root = root or get_settings().video_data_dir
    with Session(engine) as s, s.begin():
        # All request/worker acquisition serializes on the user row.
        users = list(
            s.scalars(
                select(User)
                .where(User.state.in_(("active", "deleting")))
                .order_by(User.id)
                .with_for_update()
            )
        )
        for user in users:
            for kind, model in (("asset", Asset), ("job", VideoJob)):
                expired = list(
                    s.scalars(
                        select(model).where(
                            model.user_id == user.id,
                            model.expires_at <= utcnow(),
                            model.deleted_at.is_(None),
                        )
                    )
                )
                for row in expired:
                    if dry_run:
                        print("Would expire", kind, row.id)
                        continue
                    row.deleted_at = utcnow()
                    if not s.scalar(
                        select(Deletion.id).where(
                            Deletion.kind == kind, Deletion.resource_id == row.id
                        )
                    ):
                        s.add(Deletion(user_id=user.id, kind=kind, resource_id=row.id))
            s.flush()
            # Under the user lock, prevent expired queued work from blocking forever.
            # Running work is retained until completion or operator inspection.
            for model in (VideoJob, AnalysisJob):
                for job in s.scalars(select(model).where(model.status.in_(("pending", "queued")))):
                    asset = s.get(Asset, job.asset_id) if job.asset_id else None
                    owner = asset.user_id if asset else getattr(job, "user_id", None)
                    expiry = asset.expires_at if asset else getattr(job, "expires_at", None)
                    if (
                        owner == user.id
                        and (user.state == "deleting" or (expiry and expiry <= utcnow()))
                        and not dry_run
                    ):
                        job.status, job.error_code, job.finished_at = (
                            "failed",
                            "RESOURCE_EXPIRED",
                            utcnow(),
                        )
            s.flush()
            if user.state == "deleting" and not dry_run:
                for upload in s.scalars(
                    select(SnsUpload).where(
                        SnsUpload.owner == str(user.id), SnsUpload.status == "queued"
                    )
                ):
                    upload.status, upload.error_code, upload.finished_at = (
                        "failed",
                        "ACCOUNT_DELETING",
                        utcnow(),
                    )
            for item in s.scalars(
                select(Deletion)
                .where(Deletion.user_id == user.id, Deletion.state.in_(("requested", "blocked")))
                .order_by(Deletion.created_at)
            ):
                if dry_run:
                    print("Would process", item.id)
                    continue
                if s.scalar(
                    select(ResourceUse.id).where(ResourceUse.user_id == user.id).limit(1)
                ) or active_jobs(s, item.kind, item.resource_id):
                    item.state = "blocked"
                    continue
                try:
                    # Savepoint preserves the failed attempt while rolling back partial DB edits.
                    with s.begin_nested():
                        scrub(s, item, root)
                    item.state, item.error, item.finished_at = "complete", None, utcnow()
                except (OSError, ValueError):
                    item.attempts += 1
                    item.state = "failed" if item.attempts >= 3 else "requested"
                    item.error = "CLEANUP_IO_FAILED"
        if not dry_run:
            s.execute(delete(Deletion).where(Deletion.finished_at < utcnow() - timedelta(days=30)))
            s.execute(delete(LoginState).where(LoginState.expires_at <= utcnow()))
            s.execute(delete(AuthSession).where(AuthSession.expires_at <= utcnow()))
        if dry_run:
            s.rollback()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    while True:
        sweep(dry_run=args.dry_run)
        if not args.loop:
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
