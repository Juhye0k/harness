"""Reuse immutable originals for selected candidate exports."""

from dataclasses import asdict
from uuid import uuid4

from app.adapters.media import extract
from app.domain.jobs import output_file
from app.domain.video import VideoError
from app.services.video import checksum


def execute_asset(asset, start, duration, root, data_root):
    source = output_file(data_root, asset.path)
    if checksum(source) != asset.sha256:
        raise VideoError("OUTPUT_INVALID", "저장된 원본이 변경되었습니다.")
    directory = root.resolve() / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    final = directory / "clip.mp4"
    info, checks = extract(source, final, start, duration)
    checks["source_unchanged"] = checksum(source) == asset.sha256
    if not checks["source_unchanged"]:
        final.unlink(missing_ok=True)
        raise VideoError("OUTPUT_INVALID", "원본 보존 검사를 통과하지 못했습니다.")
    return {
        "status": "succeeded",
        "run_id": directory.name,
        "output_path": str(final),
        "checks": checks,
        "media": asdict(info),
    }
