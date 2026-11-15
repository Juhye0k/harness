"""Short transactions: never hold a DB lock while encoding media."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_engine
from app.domain.jobs import JobError
from app.models import VideoJob, utcnow


class JobRepository:
    def __init__(self, engine=None):
        self.engine = engine if engine is not None else get_engine()

    def create(self, url: str, start: float) -> VideoJob:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            job = VideoJob(source_url=url, start_seconds=start)
            session.add(job)
            session.flush()
            return job

    def get(self, job_id: UUID) -> VideoJob:
        with Session(self.engine) as session:
            job = session.get(VideoJob, job_id)
            if job is None:
                raise JobError("JOB_NOT_FOUND", "작업을 찾을 수 없습니다.", 404)
            session.expunge(job)
            return job

    def dispatch(self, job_id: UUID, publish) -> VideoJob:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            job = session.scalar(select(VideoJob).where(VideoJob.id == job_id).with_for_update())
            if job is None:
                raise JobError("JOB_NOT_FOUND", "작업을 찾을 수 없습니다.", 404)
            if job.status != "pending":
                raise JobError("STATE_CONFLICT", "발행할 수 없는 작업 상태입니다.", 409, job_id)
            try:
                publish(job.id, job.task_id)
            except Exception:
                job.status = "failed"
                job.error_code = "DISPATCH_FAILED"
                job.error_message = "작업 전달에 실패했습니다. 새 요청을 보내세요."
                job.finished_at = utcnow()
            else:
                job.status = "queued"
            job.updated_at = utcnow()
            session.flush()
            return job

    def claim(self, job_id: UUID) -> VideoJob | None:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            # Lock by ID first; queued filtering could skip an uncommitted
            # pending -> queued transition while the publisher still owns the lock.
            if (
                session.scalar(select(VideoJob.id).where(VideoJob.id == job_id).with_for_update())
                is None
            ):
                return None
            return session.scalar(
                update(VideoJob)
                .where(
                    VideoJob.id == job_id,
                    VideoJob.status == "queued",
                )
                .values(status="running", started_at=utcnow(), updated_at=utcnow())
                .returning(VideoJob)
            )

    def finish(self, job_id: UUID, *, success: bool, **values) -> bool:
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                update(VideoJob)
                .where(
                    VideoJob.id == job_id,
                    VideoJob.status == "running",
                )
                .values(
                    status="succeeded" if success else "failed",
                    finished_at=utcnow(),
                    updated_at=utcnow(),
                    **values,
                )
            )
            return result.rowcount == 1

    def mark_interrupted(self, job_id: UUID, reason: str) -> bool:
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                update(VideoJob)
                .where(
                    VideoJob.id == job_id,
                    VideoJob.status.in_(("pending", "running")),
                )
                .values(
                    status="failed",
                    error_code="INTERRUPTED",
                    error_message="관리자가 실행 중단을 확인했습니다.",
                    operator_reason=reason,
                    finished_at=utcnow(),
                    updated_at=utcnow(),
                )
            )
            return result.rowcount == 1
