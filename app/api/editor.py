"""Candidate-scoped caption editing and asynchronous, immutable final exports."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr
from sqlalchemy.orm import Session

from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.caption_repository import CaptionRepository, candidate_context
from app.adapters.job_publisher import publish_video_job
from app.adapters.job_repository import JobRepository
from app.config import get_settings
from app.domain.jobs import JobError, output_file
from app.domain.portrait import clip_captions
from app.domain.shorts_subtitles import build_shorts
from app.domain.subtitles import srt
from app.models import AnalysisJob

router = APIRouter(tags=["caption editor"])
PREFIX = "/analyses/{analysis_id}/candidates/{candidate_id}"


class CaptionCue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_segment_id: StrictStr = Field(min_length=1, max_length=32)
    start_ms: StrictInt = Field(ge=0)
    end_ms: StrictInt = Field(gt=0)
    lines: list[Annotated[StrictStr, Field(min_length=1, max_length=14)]] = Field(
        min_length=1, max_length=2
    )


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_version: StrictStr = Field(max_length=80)
    cues: list[CaptionCue] = Field(min_length=1, max_length=200)
    reviewed: StrictBool = False


@router.get(PREFIX + "/editor")
def editor_data(analysis_id: UUID, candidate_id: UUID):
    repo = CaptionRepository()
    with Session(repo.engine) as session:
        candidate, analysis, _ = candidate_context(session, analysis_id, candidate_id)
        data = candidate.data
        # Recommendation payloads deliberately omit alignment internals. Reuse saved
        # source words rather than treating that minimal payload as an ASR transcript.
        selected_ids = {s["id"] for s in data["segments"]}
        segments = [
            s
            for s in AnalysisRepository(repo.engine).read_transcript(
                analysis.asset_id, analysis.config["asr_version"]
            )
            if s["id"] in selected_ids
        ]
        if {s["id"] for s in segments} != selected_ids:
            raise JobError("TRANSCRIPT_UNAVAILABLE", "후보와 저장 전사의 원 구간이 다릅니다.", 409)
        display = build_shorts(segments, data["start_ms"], data["end_ms"])
        return {
            "analysis_id": str(analysis_id),
            "candidate_id": str(candidate_id),
            "title": data["title"],
            "start_ms": data["start_ms"],
            "end_ms": data["end_ms"],
            "source_version": analysis.config["asr_version"],
            "segments": segments,
            "suggested": display,
            "latest_revision": repo.read(analysis_id, candidate_id),
        }


@router.get("/analyses/{analysis_id}/source-video")
def source_video(analysis_id: UUID):
    repo = AnalysisRepository()
    analysis = repo.get(analysis_id)
    if analysis.status != "succeeded":
        raise JobError("RESULT_NOT_READY", "완료된 영상만 재생할 수 있습니다.", 409)
    asset = repo.asset(analysis.asset_id)
    return FileResponse(
        output_file(get_settings().video_data_dir, asset.path),
        media_type="video/mp4",
        headers={"Cache-Control": "no-store"},
    )


@router.post(PREFIX + "/caption-revisions", status_code=201)
def save_revision(analysis_id: UUID, candidate_id: UUID, body: RevisionRequest):
    repo = CaptionRepository()
    with Session(repo.engine) as session:
        analysis = session.get(AnalysisJob, analysis_id)
        if analysis is None:
            raise JobError("ANALYSIS_NOT_FOUND", "분석을 찾을 수 없습니다.", 404)
        if body.source_version != analysis.config["asr_version"]:
            raise JobError("SOURCE_CHANGED", "원본 전사 버전이 다릅니다. 새로 조회하세요.", 409)
    return repo.save(analysis_id, candidate_id, [c.model_dump() for c in body.cues], body.reviewed)


@router.get(PREFIX + "/caption-revisions/{revision_id}")
def get_revision(analysis_id: UUID, candidate_id: UUID, revision_id: UUID):
    return CaptionRepository().read(analysis_id, candidate_id, revision_id)


@router.post(PREFIX + "/caption-revisions/{revision_id}/exports", status_code=202)
def render_revision(analysis_id: UUID, candidate_id: UUID, revision_id: UUID):
    repo = CaptionRepository()
    job, created = repo.export(analysis_id, candidate_id, revision_id)
    if created:
        job = JobRepository(repo.engine).dispatch(job.id, publish_video_job)
    return {
        "job_id": str(job.id),
        "revision_id": str(revision_id),
        "status": job.status,
        "status_url": f"/jobs/{job.id}",
    }


@router.get("/jobs/{job_id}/subtitles.srt")
def rendered_subtitles(job_id: UUID):
    job = JobRepository().get(job_id)
    if job.status != "succeeded":
        raise JobError("RESULT_NOT_READY", "출력 완료 후 자막을 받을 수 있습니다.", 409)
    revision = CaptionRepository().for_job(job_id)
    if revision is None:
        raise JobError("REVISION_NOT_FOUND", "편집 출력이 아닙니다.", 404)
    data, candidate, _ = revision
    cues = clip_captions(
        data["cues"], candidate["start_ms"], candidate["end_ms"] - candidate["start_ms"]
    )
    return Response(
        srt({"cues": cues}),
        media_type="application/x-subrip",
        headers={
            "Content-Disposition": f'attachment; filename="{job_id}.srt"',
            "Cache-Control": "no-store",
        },
    )
