"""Save immutable revisions; serialize version-specific render submission in PostgreSQL."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.domain.caption_edit import content_hash, validate_cues
from app.domain.jobs import JobError
from app.models import AnalysisJob, Asset, CaptionRevision, HighlightCandidate, VideoJob

ANY_REVISION = object()


def candidate_revisions(candidate_id):
    return (
        select(CaptionRevision)
        .where(CaptionRevision.candidate_id == candidate_id)
        .order_by(CaptionRevision.created_at.desc(), CaptionRevision.id)
    )


def candidate_context(s, analysis_id, candidate_id, lock=False):
    query = select(HighlightCandidate).where(
        HighlightCandidate.id == candidate_id, HighlightCandidate.analysis_id == analysis_id
    )
    candidate = s.scalar(query.with_for_update() if lock else query)
    if candidate is None:
        raise JobError("CANDIDATE_NOT_FOUND", "추천 구간을 찾을 수 없습니다.", 404)
    analysis = s.get(AnalysisJob, analysis_id)
    if analysis.status != "succeeded":
        raise JobError("RESULT_NOT_READY", "완료된 추천을 선택하세요.", 409)
    asset = s.get(Asset, analysis.asset_id)
    return candidate, analysis, asset


def revision_data(row):
    return {
        "revision_id": str(row.id),
        "source_version": row.source_version,
        "cues": row.cues,
        "reviewed": row.reviewed,
        "created_at": row.created_at,
        "render_job_id": str(row.render_job_id) if row.render_job_id else None,
    }


class CaptionRepository:
    def __init__(self, engine=None):
        self.engine = engine if engine is not None else get_engine()

    def save(self, analysis_id, candidate_id, cues, reviewed, expected_latest=ANY_REVISION):
        with Session(self.engine) as s, s.begin():
            candidate, analysis, _ = candidate_context(s, analysis_id, candidate_id, lock=True)
            data = candidate.data
            cues = validate_cues(cues, data["segments"], data["start_ms"], data["end_ms"], reviewed)
            version = analysis.config["asr_version"]
            digest = content_hash(cues, version, reviewed)
            existing = s.scalar(
                select(CaptionRevision).where(
                    CaptionRevision.candidate_id == candidate_id,
                    CaptionRevision.content_hash == digest,
                )
            )
            if expected_latest is not ANY_REVISION:
                latest = s.scalar(candidate_revisions(candidate_id).limit(1))
                latest_id = latest.id if latest else None
                if latest_id != expected_latest and (existing is None or latest_id != existing.id):
                    raise JobError(
                        "REVISION_CONFLICT",
                        "다른 편집본이 저장됐습니다. 최신 버전을 확인하세요.",
                        409,
                    )
            if existing:
                return revision_data(existing)
            row = CaptionRevision(
                candidate_id=candidate_id,
                source_version=version,
                content_hash=digest,
                cues=cues,
                reviewed=reviewed,
            )
            s.add(row)
            s.flush()
            return revision_data(row)

    def read(self, analysis_id, candidate_id, revision_id=None):
        with Session(self.engine) as s:
            # Scope every revision by the analysis and candidate in the URL.
            candidate_context(s, analysis_id, candidate_id)
            query = candidate_revisions(candidate_id)
            if revision_id:
                query = query.where(CaptionRevision.id == revision_id)
            row = s.scalar(query.limit(1))
            if revision_id and row is None:
                raise JobError("REVISION_NOT_FOUND", "편집 버전을 찾을 수 없습니다.", 404)
            return revision_data(row) if row else None

    def recent(self, session, candidate_id):
        rows = session.scalars(candidate_revisions(candidate_id).limit(2)).all()
        return (
            revision_data(rows[0]) if rows else None,
            str(rows[1].id) if len(rows) > 1 else None,
        )

    def export(self, analysis_id, candidate_id, revision_id):
        with Session(self.engine, expire_on_commit=False) as s, s.begin():
            candidate, analysis, asset = candidate_context(s, analysis_id, candidate_id, lock=True)
            row = s.scalar(
                select(CaptionRevision)
                .where(
                    CaptionRevision.id == revision_id, CaptionRevision.candidate_id == candidate_id
                )
                .with_for_update()
            )
            if row is None:
                raise JobError("REVISION_NOT_FOUND", "편집 버전을 찾을 수 없습니다.", 404)
            if not row.reviewed or row.source_version != analysis.config["asr_version"]:
                raise JobError(
                    "SUBTITLE_REVIEW_REQUIRED", "원음과 자막을 확인한 버전을 먼저 저장하세요.", 409
                )
            if row.render_job_id:
                existing = s.get(VideoJob, row.render_job_id)
                if existing.deleted_at:
                    raise JobError(
                        "RESOURCE_GONE", "삭제한 출력입니다. 새 편집본을 저장하세요.", 410
                    )
                return existing, False
            data = candidate.data
            # Keep the original candidate's extraction cache independent from final rendering.
            job = VideoJob(
                source_url=asset.source_url,
                asset_id=asset.id,
                user_id=asset.user_id,
                legacy=asset.legacy,
                expires_at=asset.expires_at,
                start_seconds=data["start_ms"] / 1000,
                duration_seconds=(data["end_ms"] - data["start_ms"]) / 1000,
            )
            s.add(job)
            s.flush()
            row.render_job_id = job.id
            s.flush()
            return job, True

    def for_job(self, job_id):
        with Session(self.engine) as s:
            row = s.scalar(select(CaptionRevision).where(CaptionRevision.render_job_id == job_id))
            if row is None:
                return None
            candidate = s.get(HighlightCandidate, row.candidate_id)
            analysis = s.get(AnalysisJob, candidate.analysis_id)
            return revision_data(row), candidate.data, analysis.asset_id
