"""Local-only recommendations API, without exposing source URLs or provider secrets."""

from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from app.adapters.ai import PROMPT_VERSION, enabled, provider_config
from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.download import validate_url
from app.adapters.job_publisher import publish_analysis_job, publish_video_job
from app.adapters.job_repository import JobRepository
from app.config import get_settings
from app.domain.jobs import JobError
from app.domain.recommendations import VERSION
from app.domain.subtitles import VERSION as SUBTITLE_VERSION
from app.domain.subtitles import build_subtitles, srt
from app.domain.video import VideoError

router = APIRouter(tags=["recommendations"])


class AnalysisRequest(BaseModel):
    mode: Literal["transcription", "recommendation"] = "recommendation"
    url: str | None = Field(default=None, min_length=1, max_length=4096)
    asset_id: UUID | None = None
    genre: Literal["conversation", "drama_movie", "game", "entertainment", "sports", "unknown"] = (
        "unknown"
    )
    purpose: Literal["balanced", "information", "humor", "emotion", "suspense"] = "balanced"

    @model_validator(mode="after")
    def source(self):
        if (self.url is None) == (self.asset_id is None):
            raise ValueError("Exactly one source is required")
        return self


def repository():
    return AnalysisRepository()


def publisher():
    return publish_analysis_job


@router.post("/analyses", status_code=202)
def create_analysis(
    body: AnalysisRequest,
    repo: Annotated[AnalysisRepository, Depends(repository)],
    publish: Annotated[Callable, Depends(publisher)],
):
    settings = get_settings()
    try:
        enabled(settings, body.mode)
    except VideoError as exc:
        raise JobError(exc.code, str(exc), 503) from exc
    url = validate_url(body.url)[1] if body.url else None
    job = repo.create(
        url,
        body.asset_id,
        body.genre,
        body.purpose,
        {
            **provider_config(settings, body.mode),
            "prompt_version": PROMPT_VERSION,
            "ranking_version": VERSION,
        },
    )
    job = repo.dispatch(job.id, publish)
    # A failed dispatch still returns a trackable resource, never an untraceable retry hint.
    return {"analysis_id": str(job.id), "status": job.status, "status_url": f"/analyses/{job.id}"}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]):
    job = repo.get(analysis_id)
    return {
        "analysis_id": str(job.id),
        "asset_id": str(job.asset_id),
        "status": job.status,
        "stage": job.stage,
        "genre": job.genre,
        "purpose": job.purpose,
        "analysis_basis": "한국어 음성 전사 기반 · 시각 장면 분석 없음",
        "config": job.config,
        "outcome": job.outcome,
        "error": {
            "code": job.error_code,
            "message": "분석이 완료되지 못했습니다. 오류 코드를 확인하세요.",
        }
        if job.error_code
        else None,
        "candidates": repo.candidates(job.id) if job.status == "succeeded" else [],
    }


@router.get("/analyses/{analysis_id}/transcript")
def get_transcript(analysis_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]):
    job = repo.get(analysis_id)
    if job.status != "succeeded":
        raise JobError("RESULT_NOT_READY", "완료된 분석의 전사만 조회할 수 있습니다.", 409)
    return {
        "analysis_id": str(job.id),
        "asset_id": str(job.asset_id),
        "version": job.config["asr_version"],
        "segments": repo.read_transcript(job.asset_id, job.config["asr_version"]),
    }


@router.get("/analyses/{analysis_id}/subtitles")
def get_subtitles(analysis_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]):
    transcript = get_transcript(analysis_id, repo)
    return {
        "analysis_id": str(analysis_id),
        "transcript_version": transcript["version"],
        **build_subtitles(transcript["segments"]),
    }


@router.get("/analyses/{analysis_id}/subtitles.srt")
def download_subtitles(analysis_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]):
    filename = f"subtitles-{analysis_id}-{SUBTITLE_VERSION}.srt"
    return Response(
        srt(get_subtitles(analysis_id, repo)),
        media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/analyses/{analysis_id}/candidates/{candidate_id}/exports", status_code=202)
def export_candidate(
    analysis_id: UUID, candidate_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]
):
    job, created = repo.export(analysis_id, candidate_id)
    if created:
        job = JobRepository(repo.engine).dispatch(job.id, publish_video_job)
    return {"job_id": str(job.id), "status": job.status, "status_url": f"/jobs/{job.id}"}
