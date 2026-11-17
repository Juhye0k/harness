"""Local-only recommendations API, without exposing source URLs or provider secrets."""

from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from app.adapters.ai import PROMPT_VERSION, enabled, provider_config
from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.analysis_requests import create_once, input_hash, lookup
from app.adapters.download import validate_url
from app.adapters.job_publisher import publish_analysis_job, publish_video_job
from app.adapters.job_repository import JobRepository
from app.config import get_settings
from app.domain.jobs import JobError
from app.domain.recommendations import VERSION
from app.domain.shorts_subtitles import build_shorts
from app.domain.subtitles import build_subtitles, srt
from app.domain.video import VideoError

router = APIRouter(tags=["recommendations"])


class AnalysisRequest(BaseModel):
    request_id: UUID | None = None
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
    url = validate_url(body.url)[1] if body.url else None
    settings = get_settings()

    def config():
        try:
            enabled(settings, body.mode)
        except VideoError as exc:
            raise JobError(exc.code, str(exc), 503) from exc
        return {
            **provider_config(settings, body.mode),
            "prompt_version": PROMPT_VERSION,
            "ranking_version": VERSION,
        }

    if body.request_id:
        values = {**body.model_dump(mode="json", exclude={"request_id"}), "url": url}
        digest = input_hash(values)
        job = lookup(repo, body.request_id, digest)
        if job is None:
            job, created = create_once(
                repo, body.request_id, digest, url, body.asset_id, body.genre, body.purpose, config
            )
            if created:
                job = repo.dispatch(job.id, publish)
    else:
        # Legacy clients retain the original contract; response-loss recovery requires a key.
        resolved_config = config()
        job = repo.create(url, body.asset_id, body.genre, body.purpose, resolved_config)
        job = repo.dispatch(job.id, publish)
    # A failed dispatch still returns a trackable resource, never an untraceable retry hint.
    return {"analysis_id": str(job.id), "status": job.status, "status_url": f"/analyses/{job.id}"}


@router.get("/analysis-requests/{request_id}")
def analysis_request(request_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]):
    job = lookup(repo, request_id)
    if job is None:
        raise JobError(
            "REQUEST_NOT_FOUND", "아직 접수를 확인하지 못했습니다. 다시 조회하세요.", 404
        )
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
            "message": (
                "제공자가 요청 접근을 거부했습니다. "
                "키 인증과 별도로 제공자 권한·요청 제한을 확인하세요."
                if job.error_code == "PROVIDER_ACCESS_DENIED"
                else "분석이 완료되지 못했습니다. 오류 코드를 확인하세요."
            ),
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
def get_subtitles(
    analysis_id: UUID,
    repo: Annotated[AnalysisRepository, Depends(repository)],
    profile: Literal["ko-display-v1", "shorts-display-v1"] = "ko-display-v1",
    start_ms: Annotated[int | None, Query(ge=0)] = None,
    end_ms: Annotated[int | None, Query(gt=0)] = None,
):
    transcript = get_transcript(analysis_id, repo)
    try:
        if profile == "shorts-display-v1":
            if end_ms is not None and end_ms > repo.asset(transcript["asset_id"]).duration_ms:
                raise ValueError()
            data = build_shorts(transcript["segments"], start_ms, end_ms)
        else:
            if start_ms is not None or end_ms is not None:
                raise ValueError()
            data = build_subtitles(transcript["segments"])
    except ValueError as exc:
        raise JobError("INVALID_RANGE", "Invalid subtitle range", 422) from exc
    return {"analysis_id": str(analysis_id), "transcript_version": transcript["version"], **data}


@router.get("/analyses/{analysis_id}/subtitles.srt")
def download_subtitles(
    analysis_id: UUID,
    repo: Annotated[AnalysisRepository, Depends(repository)],
    profile: Literal["ko-display-v1", "shorts-display-v1"] = "ko-display-v1",
    start_ms: Annotated[int | None, Query(ge=0)] = None,
    end_ms: Annotated[int | None, Query(gt=0)] = None,
):
    data = get_subtitles(analysis_id, repo, profile, start_ms, end_ms)
    if profile == "shorts-display-v1" and not data["quality_pass"]:
        raise JobError("SUBTITLE_REVIEW_REQUIRED", "Subtitle review required", 409)
    filename = f"subtitles-{analysis_id}-{data['version']}.srt"
    return Response(
        srt(data),
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
