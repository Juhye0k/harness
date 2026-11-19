"""Save immutable revisions; serialize version-specific render submission in PostgreSQL."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.domain.caption_edit import content_hash, validate_cues
from app.domain.jobs import JobError
from app.domain.portrait import (
    EDITED_PROFILE,
    LEGACY_EDITED_PROFILE,
    render_input_hash,
    visible_spans,
)
from app.domain.video import VideoError
from app.models import (
    AnalysisJob,
    Asset,
    CaptionRenderJob,
    CaptionRevision,
    HighlightCandidate,
    VideoJob,
)

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


def revision_data(row, render=None):
    job_id = render.job_id if render else row.render_job_id
    return {
        "revision_id": str(row.id),
        "source_version": row.source_version,
        "cues": row.cues,
        "reviewed": row.reviewed,
        "created_at": row.created_at,
        "render_job_id": str(job_id) if job_id else None,
        "render_profile": (render.profile if render else LEGACY_EDITED_PROFILE) if job_id else None,
    }


def latest_render(session, row):
    return session.scalar(
        select(CaptionRenderJob)
        .join(VideoJob, VideoJob.id == CaptionRenderJob.job_id)
        .where(CaptionRenderJob.revision_id == row.id, CaptionRenderJob.profile == EDITED_PROFILE)
        .order_by(VideoJob.created_at.desc(), CaptionRenderJob.job_id)
        .limit(1)
    )


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
                return revision_data(existing, latest_render(s, existing))
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
            return revision_data(row, latest_render(s, row)) if row else None

    def recent(self, session, candidate_id):
        rows = session.scalars(candidate_revisions(candidate_id).limit(2)).all()
        return (
            revision_data(rows[0], latest_render(session, rows[0])) if rows else None,
            str(rows[1].id) if len(rows) > 1 else None,
        )

    def export(self, analysis_id, candidate_id, revision_id, source_captions=None):
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
            data = candidate.data
            spans = []
            if source_captions is not None:
                if source_captions["source_sha256"] != asset.sha256:
                    raise JobError(
                        "SOURCE_CAPTIONS_MISMATCH", "원본 자막 관측이 현재 영상과 다릅니다.", 409
                    )
                try:
                    spans = visible_spans(
                        source_captions["visible_spans"], data["start_ms"], data["end_ms"]
                    )
                except VideoError as exc:
                    raise JobError(exc.code, str(exc), 422) from exc
            digest = render_input_hash(EDITED_PROFILE, asset.sha256, spans)
            render = s.scalar(
                select(CaptionRenderJob).where(
                    CaptionRenderJob.revision_id == row.id,
                    CaptionRenderJob.input_hash == digest,
                )
            )
            if render:
                existing = s.get(VideoJob, render.job_id)
                if existing.deleted_at:
                    raise JobError(
                        "RESOURCE_GONE", "삭제한 출력입니다. 새 편집본을 저장하세요.", 410
                    )
                return existing, False
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
            s.add(
                CaptionRenderJob(
                    job_id=job.id,
                    revision_id=row.id,
                    profile=EDITED_PROFILE,
                    input_hash=digest,
                    source_caption_spans=spans,
                )
            )
            s.flush()
            return job, True

    def for_job(self, job_id):
        with Session(self.engine) as s:
            render = s.get(CaptionRenderJob, job_id)
            row = (
                s.get(CaptionRevision, render.revision_id)
                if render
                else s.scalar(
                    select(CaptionRevision).where(CaptionRevision.render_job_id == job_id)
                )
            )
            if row is None:
                return None
            candidate = s.get(HighlightCandidate, row.candidate_id)
            analysis = s.get(AnalysisJob, candidate.analysis_id)
            saved = revision_data(row, render)
            saved["source_caption_spans"] = render.source_caption_spans if render else []
            saved["render_input_hash"] = render.input_hash if render else None
            return saved, candidate.data, analysis.asset_id
