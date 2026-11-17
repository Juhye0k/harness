"""Read-only verification endpoints. No subprocesses, encoding, or provider calls."""

import json
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.adapters.analysis_repository import AnalysisRepository
from app.adapters.verification_record import code_status
from app.api.analyses import get_transcript, repository
from app.config import get_settings
from app.domain.jobs import JobError
from app.domain.shorts_subtitles import build_shorts
from app.domain.subtitles import build_subtitles
from app.services.transcript_review import report

router = APIRouter()


@router.get("/analyses/{analysis_id}/verification")
def verification(analysis_id: UUID, repo: Annotated[AnalysisRepository, Depends(repository)]):
    job = repo.get(analysis_id)
    result = {
        "analysis_id": str(job.id),
        "processing": job.status,
        "code": code_status(),
        "display": None,
        "transcript_human_review": {"status": "pending"},
        "cer": None,
    }
    if job.status != "succeeded":
        return result
    transcript = get_transcript(analysis_id, repo)
    segments = transcript["segments"]
    fast = build_shorts(segments)
    legacy = build_subtitles(segments)
    human = report(repo, analysis_id)
    confirmed = sum(row["decision"] in ("ok", "error") for row in human["segments"])
    result.update(
        display=fast,
        baseline={
            "version": legacy["version"],
            "cues": len(legacy["cues"]),
            "constraint_flagged": sum(
                bool(
                    set(c["warnings"])
                    - {"WORD_TIMESTAMPS_UNAVAILABLE", "UNALIGNED_WORD_TIMESTAMPS"}
                )
                for c in legacy["cues"]
            ),
        },
        transcript_human_review={
            "status": "complete" if segments and confirmed == len(segments) else "pending",
            "confirmed": confirmed,
            "total": len(segments),
        },
    )
    return result


@router.get("/analyses/{analysis_id}/verification/assets/{asset_id}")
def verification_asset(
    analysis_id: UUID, asset_id: str, repo: Annotated[AnalysisRepository, Depends(repository)]
):
    repo.get(analysis_id)
    if not re.fullmatch(r"[a-z0-9-]+\.(png|mp4|html)", asset_id):
        raise JobError("ASSET_NOT_FOUND", "Asset not found", 404)
    root = (get_settings().video_data_dir / "verification" / str(analysis_id)).resolve()
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        path = (root / manifest[asset_id]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise JobError("ASSET_NOT_FOUND", "Asset not found", 404) from None
    return FileResponse(path, headers={"Cache-Control": "no-store"})
