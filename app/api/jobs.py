"""Local-only job API. Authentication is required before external deployment."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from app.adapters.job_publisher import publish_video_job
from app.adapters.job_repository import JobRepository
from app.config import get_settings
from app.domain.jobs import JobError, output_file
from app.services.jobs import submit

router = APIRouter(prefix="/jobs", tags=["video jobs"])


class ExtractionRequest(BaseModel):
    url: str | None = Field(default=None, min_length=1, max_length=4096)
    asset_id: UUID | None = None

    @model_validator(mode="after")
    def source(self):
        if (self.url is None) == (self.asset_id is None):
            raise ValueError("Exactly one source is required")
        return self

    start_seconds: float = Field(ge=0, allow_inf_nan=False)


def repository():
    return JobRepository()


def publisher():
    return publish_video_job


@router.post("/video-extractions", status_code=202)
def create_job(
    body: ExtractionRequest,
    request: Request,
    repo: Annotated[JobRepository, Depends(repository)],
    publish: Annotated[Callable, Depends(publisher)],
):
    if body.asset_id:
        job = repo.create_from_asset(body.asset_id, body.start_seconds)
        job = repo.dispatch(job.id, publish)
    else:
        job = submit(repo, publish, body.url, body.start_seconds)
    return {
        "job_id": str(job.id),
        "status": job.status,
        "status_url": str(request.url_for("get_job", job_id=job.id)),
    }


@router.get("/{job_id}", name="get_job")
def get_job(job_id: UUID, repo: Annotated[JobRepository, Depends(repository)]):
    job = repo.get(job_id)
    return {
        "job_id": str(job.id),
        "status": job.status,
        "start_seconds": job.start_seconds,
        "duration_seconds": job.duration_seconds,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error": {"code": job.error_code, "message": job.error_message} if job.error_code else None,
        "result": job.result if job.status == "succeeded" else None,
        "download_url": f"/jobs/{job.id}/download" if job.status == "succeeded" else None,
    }


@router.get("/{job_id}/download")
def download_job(job_id: UUID, repo: Annotated[JobRepository, Depends(repository)]):
    job = repo.get(job_id)
    if job.status != "succeeded":
        raise JobError("RESULT_NOT_READY", "검증된 결과가 아직 없습니다.", 409)
    path = output_file(get_settings().video_data_dir, job.output_path)
    return FileResponse(path, media_type="video/mp4", filename=f"{job.id}.mp4")
