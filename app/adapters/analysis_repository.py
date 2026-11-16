"""Short transactions, persistent claims, no external call while holding a media lock."""

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import get_engine
from app.domain.jobs import JobError
from app.domain.video import VideoError
from app.models import (
    AnalysisJob,
    Asset,
    HighlightCandidate,
    ProviderCall,
    Transcript,
    TranscriptReview,
    VideoJob,
    utcnow,
)


class AnalysisRepository:
    def __init__(self, engine=None):
        self.engine = engine if engine is not None else get_engine()

    def create(self, url, asset_id, genre, purpose, config):
        with Session(self.engine, expire_on_commit=False) as s, s.begin():
            if asset_id:
                asset = s.get(Asset, asset_id)
                if asset is None or asset.state != "ready":
                    raise JobError("ASSET_NOT_READY", "사용할 수 있는 원본이 없습니다.", 409)
            else:
                asset = Asset(source_url=url)
                s.add(asset)
                s.flush()
            job = AnalysisJob(asset_id=asset.id, genre=genre, purpose=purpose, config=config)
            s.add(job)
            s.flush()
            return job

    def get(self, job_id):
        with Session(self.engine) as s:
            job = s.get(AnalysisJob, job_id)
            if job is None:
                raise JobError("ANALYSIS_NOT_FOUND", "분석을 찾을 수 없습니다.", 404)
            s.expunge(job)
            return job

    def dispatch(self, job_id, publish):
        with Session(self.engine, expire_on_commit=False) as s, s.begin():
            job = s.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update())
            if job is None or job.status != "pending":
                raise JobError("STATE_CONFLICT", "발행할 수 없는 분석입니다.", 409)
            try:
                publish(job.id, job.task_id)
            except Exception:
                job.status, job.error_code = "failed", "DISPATCH_FAILED"
                job.finished_at = utcnow()
            else:
                job.status = "queued"
            job.updated_at = utcnow()
            s.flush()
            return job

    def claim(self, job_id):
        with Session(self.engine, expire_on_commit=False) as s, s.begin():
            job = s.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update())
            if job is None or job.status != "queued":
                return None
            job.status, job.updated_at = "running", utcnow()
            s.flush()
            return job

    def stage(self, job_id, stage):
        with Session(self.engine) as s, s.begin():
            changed = s.execute(
                update(AnalysisJob)
                .where(AnalysisJob.id == job_id, AnalysisJob.status == "running")
                .values(stage=stage, updated_at=utcnow())
            ).rowcount
            if not changed:
                raise VideoError("INTERRUPTED", "분석 실행이 중단되었습니다.")

    def asset(self, asset_id):
        with Session(self.engine) as s:
            asset = s.get(Asset, asset_id)
            s.expunge(asset)
            return asset

    def save_asset(self, asset_id, **values):
        with Session(self.engine) as s, s.begin():
            s.execute(update(Asset).where(Asset.id == asset_id).values(**values))

    def transcript(self, asset_id, version):
        with Session(self.engine, expire_on_commit=False) as s, s.begin():
            # Unique key is also a persistent ASR claim. Never retry an uncertain paid call.
            owned = s.scalar(
                insert(Transcript)
                .values(asset_id=asset_id, version=version, state="running")
                .on_conflict_do_nothing()
                .returning(Transcript.id)
            )
            item = s.scalar(
                select(Transcript).where(
                    Transcript.asset_id == asset_id, Transcript.version == version
                )
            )
            if not owned and item.state != "succeeded":
                raise VideoError("TRANSCRIPT_UNAVAILABLE", "전사가 진행 중이거나 실패했습니다.")
            return item, bool(owned)

    def save_transcript(self, transcript_id, segments=None, failed=False):
        with Session(self.engine) as s, s.begin():
            s.execute(
                update(Transcript)
                .where(Transcript.id == transcript_id, Transcript.state == "running")
                .values(state="failed" if failed else "succeeded", segments=segments)
            )

    def read_transcript(self, asset_id, version):
        # Read-only: GET must never acquire an ASR claim or create a transcript.
        with Session(self.engine) as s:
            item = s.scalar(
                select(Transcript).where(
                    Transcript.asset_id == asset_id,
                    Transcript.version == version,
                    Transcript.state == "succeeded",
                )
            )
            if item is None:
                raise JobError("TRANSCRIPT_UNAVAILABLE", "전사 결과를 찾을 수 없습니다.", 404)
            return item.segments

    def review_decisions(self, analysis_id, asr_version, policy_version):
        with Session(self.engine) as s:
            rows = s.scalars(
                select(TranscriptReview).where(
                    TranscriptReview.analysis_id == analysis_id,
                    TranscriptReview.asr_version == asr_version,
                    TranscriptReview.policy_version == policy_version,
                )
            )
            return {
                r.segment_id: {"decision": r.decision, "note": r.note, "revision": r.revision}
                for r in rows
            }

    def save_review(self, analysis_id, asr_version, policy_version, segment_id, body):
        with Session(self.engine) as s, s.begin():
            # Serialize first inserts as well as updates; no lost writes across browser tabs.
            s.scalar(select(AnalysisJob).where(AnalysisJob.id == analysis_id).with_for_update())
            row = s.scalar(
                select(TranscriptReview).where(
                    TranscriptReview.analysis_id == analysis_id,
                    TranscriptReview.asr_version == asr_version,
                    TranscriptReview.policy_version == policy_version,
                    TranscriptReview.segment_id == segment_id,
                )
            )
            if (row.revision if row else 0) != body.revision:
                raise JobError("REVIEW_CONFLICT", "다른 검수가 저장됐습니다. 새로 조회하세요.", 409)
            if row is None:
                row = TranscriptReview(
                    analysis_id=analysis_id,
                    asr_version=asr_version,
                    policy_version=policy_version,
                    segment_id=segment_id,
                    revision=0,
                )
                s.add(row)
            row.decision, row.note = body.decision, body.note
            row.revision += 1
            row.updated_at = utcnow()
            s.flush()
            return {"decision": row.decision, "note": row.note, "revision": row.revision}

    def call_start(self, job_id, stage):
        with Session(self.engine) as s, s.begin():
            s.add(ProviderCall(analysis_id=job_id, stage=stage))

    def call_finish(self, job_id, stage, state, metadata):
        with Session(self.engine) as s, s.begin():
            s.execute(
                update(ProviderCall)
                .where(ProviderCall.analysis_id == job_id, ProviderCall.stage == stage)
                .values(state=state, metadata_json=metadata)
            )

    def finish(self, job_id, selected=(), rejected=(), error=None, outcome=None):
        with Session(self.engine) as s, s.begin():
            job = s.scalar(select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update())
            if job is None or job.status != "running":
                return False
            for rank, data in enumerate(selected, 1):
                s.add(HighlightCandidate(analysis_id=job_id, rank=rank, data=data))
            job.status = "failed" if error else "succeeded"
            job.error_code, job.outcome, job.rejected = error, outcome, list(rejected)
            job.finished_at = job.updated_at = utcnow()
            if not error:
                job.stage = "complete"
            return True

    def candidates(self, job_id):
        with Session(self.engine) as s:
            rows = s.execute(
                select(HighlightCandidate, VideoJob.id)
                .outerjoin(VideoJob, VideoJob.candidate_id == HighlightCandidate.id)
                .where(HighlightCandidate.analysis_id == job_id)
                .order_by(HighlightCandidate.rank)
            ).all()
            return [
                {
                    **c.data,
                    "id": str(c.id),
                    "rank": c.rank,
                    "export_job_id": str(export_id) if export_id else None,
                }
                for c, export_id in rows
            ]

    def export(self, job_id, candidate_id):
        with Session(self.engine, expire_on_commit=False) as s, s.begin():
            candidate = s.scalar(
                select(HighlightCandidate)
                .where(
                    HighlightCandidate.id == candidate_id, HighlightCandidate.analysis_id == job_id
                )
                .with_for_update()
            )
            if candidate is None:
                raise JobError("CANDIDATE_NOT_FOUND", "추천 구간을 찾을 수 없습니다.", 404)
            analysis = s.get(AnalysisJob, job_id)
            if analysis.status != "succeeded":
                raise JobError("RESULT_NOT_READY", "분석이 완료되지 않았습니다.", 409)
            existing = s.scalar(select(VideoJob).where(VideoJob.candidate_id == candidate_id))
            if existing:
                return existing, False
            asset = s.get(Asset, analysis.asset_id)
            data = candidate.data
            job = VideoJob(
                source_url=asset.source_url,
                asset_id=asset.id,
                candidate_id=candidate_id,
                start_seconds=data["start_ms"] / 1000,
                duration_seconds=(data["end_ms"] - data["start_ms"]) / 1000,
            )
            s.add(job)
            s.flush()
            return job, True

    def mark_interrupted(self, job_id, reason):
        with Session(self.engine) as s, s.begin():
            return (
                s.execute(
                    update(AnalysisJob)
                    .where(AnalysisJob.id == job_id, AnalysisJob.status.in_(("pending", "running")))
                    .values(
                        status="failed",
                        error_code="INTERRUPTED",
                        operator_reason=reason,
                        updated_at=utcnow(),
                        finished_at=utcnow(),
                    )
                ).rowcount
                == 1
            )
