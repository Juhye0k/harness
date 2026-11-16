"""Local-only review API. No decoding, downloading or model calls on GET."""

import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.adapters.analysis_repository import AnalysisRepository
from app.api.analyses import repository
from app.config import get_settings
from app.domain.jobs import JobError, output_file
from app.services import transcript_review as service

router = APIRouter(tags=["transcript review"])


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript_version: str = Field(max_length=80)
    policy_version: str = Field(max_length=80)
    decision: Literal["error", "ok", "uncertain"]
    note: str = Field(default="", max_length=1000)
    revision: int = Field(ge=0, strict=True)


@router.get("/analyses/{analysis_id}/transcript-review")
def get_review(analysis_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]):
    return service.report(repo, analysis_id)


@router.put("/analyses/{analysis_id}/transcript-review/{segment_id}")
def put_review(
    analysis_id: UUID,
    segment_id: str,
    body: Decision,
    repo: Annotated[AnalysisRepository, Depends(repository)],
):
    return service.decide(repo, analysis_id, segment_id, body)


@router.get("/analyses/{analysis_id}/review-audio")
def review_audio(analysis_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]):
    job, _ = service.transcript(repo, analysis_id)
    asset = repo.asset(job.asset_id)
    root = get_settings().video_data_dir
    try:
        source = output_file(root, asset.path)
    except JobError as exc:
        raise JobError("AUDIO_NOT_FOUND", "검수 음성을 찾을 수 없습니다.", 404) from exc
    version = job.config["asr_version"]
    # Versions come from stored config, but must never become arbitrary path components.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", version):
        raise JobError("AUDIO_NOT_FOUND", "검수 음성을 찾을 수 없습니다.", 404)
    name = "audio.mp3" if job.config.get("transcription_provider") == "groq" else "audio.wav"
    path = source.parent / version / name
    if not path.is_file():
        raise JobError("AUDIO_NOT_FOUND", "저장된 검수 음성이 없습니다.", 404)
    try:
        path = output_file(root, path.relative_to(root.resolve()).as_posix())
    except JobError as exc:
        raise JobError("AUDIO_NOT_FOUND", "검수 음성을 찾을 수 없습니다.", 404) from exc
    return FileResponse(
        path,
        media_type="audio/mpeg" if name.endswith("mp3") else "audio/wav",
        headers={"Cache-Control": "no-store"},
    )
