"""Uploaded bytes are validated offline and copied once into managed originals."""

import os
import shutil

from app.adapters.media import probe
from app.domain.jobs import JobError
from app.domain.video import MAX_BYTES, MAX_SECONDS, VideoError
from app.services.access import worker_guard
from app.services.video import checksum


def upload_directory(root, asset_id):
    from uuid import UUID

    name = str(UUID(str(asset_id)))
    root = root.resolve()
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise JobError("INVALID_UPLOAD_PATH", "업로드 경로를 사용할 수 없습니다.", 409)
    return path


@worker_guard("asset", "repo")
def validate_upload(asset_id, repo, settings):
    try:
        receipt = repo.claim(asset_id, "queued", "validating")
    except JobError:
        return
    target_dir = settings.video_data_dir.resolve() / "assets" / str(asset_id)
    target = target_dir / "source.bin"
    temporary = target_dir / "source.part"
    created = False
    try:
        source = upload_directory(settings.upload_data_dir, asset_id) / "received.bin"
        if source.stat().st_size != receipt.expected_bytes or source.stat().st_size > MAX_BYTES:
            raise VideoError("UPLOAD_INCOMPLETE", "전송 크기가 일치하지 않습니다.")
        if checksum(source) != receipt.sha256:
            raise VideoError("SOURCE_CHANGED", "업로드 원본이 변경됐습니다.")
        info = probe(source)
        if info.duration > MAX_SECONDS:
            raise VideoError("LIMIT_EXCEEDED", "원본 영상은 20분 이하여야 합니다.")
        target_dir.mkdir(parents=True, exist_ok=False)
        created = True
        with source.open("rb") as src, temporary.open("xb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        if checksum(temporary) != receipt.sha256:
            raise VideoError("SOURCE_CHANGED", "원본 보존 검사를 통과하지 못했습니다.")
        os.link(temporary, target)
        temporary.unlink()
        saved = repo.finish(
            asset_id,
            path=target.relative_to(settings.video_data_dir.resolve()).as_posix(),
            sha256=receipt.sha256,
            duration_ms=round(info.duration * 1000),
            has_audio=info.has_audio,
        )
        if saved:
            source.unlink()
    except (OSError, VideoError, JobError) as exc:
        repo.finish(
            asset_id,
            error=exc.code if isinstance(exc, (VideoError, JobError)) else "UPLOAD_IO_FAILED",
        )
        if created:
            temporary.unlink(missing_ok=True)
        # Preserve rejected bytes until their registered 7-day deletion; never retry automatically.
