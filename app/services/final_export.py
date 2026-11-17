"""Render exactly the confirmed editor snapshot; no AI or network in this path."""

from uuid import uuid4

from app.adapters.media import probe
from app.adapters.portrait import render_portrait
from app.domain.caption_edit import PROFILE, validate_cues
from app.domain.jobs import output_file
from app.domain.video import VideoError
from app.services.video import checksum


def execute_final(asset, job, revision, root, data_root):
    saved, candidate, asset_id = revision
    if asset_id != asset.id or not saved["reviewed"]:
        raise VideoError("SUBTITLE_INVALID", "확정한 편집본과 원본이 일치하지 않습니다.")
    validate_cues(
        saved["cues"], candidate["segments"], candidate["start_ms"], candidate["end_ms"], True
    )
    if (int(round(job.start_seconds * 1000)), int(round(job.duration_seconds * 1000))) != (
        candidate["start_ms"],
        candidate["end_ms"] - candidate["start_ms"],
    ):
        raise VideoError("INVALID_RANGE", "확정한 출력 구간과 작업이 다릅니다.")
    source = output_file(data_root, asset.path)
    if checksum(source) != asset.sha256:
        raise VideoError("OUTPUT_INVALID", "원본 보존 검사를 통과하지 못했습니다.")
    directory = root.resolve() / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    target = directory / "clip.mp4"
    try:
        rendered = render_portrait(
            source,
            target,
            saved["cues"],
            candidate["start_ms"],
            candidate["end_ms"] - candidate["start_ms"],
        )
        info = probe(target, output=True)
        if checksum(source) != asset.sha256:
            raise VideoError("OUTPUT_INVALID", "원본 보존 검사를 통과하지 못했습니다.")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {
        "status": "succeeded",
        "run_id": directory.name,
        "output_path": str(target),
        "media": {
            "duration": info.duration,
            "container_duration": info.container_duration,
            "has_audio": info.has_audio,
            "width": rendered["width"],
            "height": rendered["height"],
        },
        "checks": rendered["checks"],
        "render": {
            "profile": PROFILE,
            "revision_id": saved["revision_id"],
            "subtitle_time_origin": "clip",
        },
    }
