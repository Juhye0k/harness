"""One synchronous use case, independent of HTTP, databases and Celery."""

import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from yt_dlp.version import __version__ as yt_dlp_version

from app.adapters.download import validate_url
from app.adapters.media import extract
from app.adapters.process import executable, run
from app.domain.video import MAX_BYTES, TOLERANCE, VideoError, validate_start


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url: str, directory: Path) -> Path:
    raw = run(
        [sys.executable, "-m", "app.adapters.fetch_worker"],
        300,
        watch_dir=directory,
        max_bytes=MAX_BYTES,
        input_text=json.dumps({"url": url, "directory": str(directory)}),
    )
    try:
        result = json.loads(raw)
        if "error" in result:
            raise VideoError(result["error"], result["message"])
        path = Path(result["path"]).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError()
        if path.stat().st_size > MAX_BYTES:
            raise VideoError("LIMIT_EXCEEDED", "다운로드가 500MiB를 넘었습니다.")
        return path
    except (ValueError, KeyError, TypeError) as exc:
        raise VideoError("DOWNLOAD_FAILED", "다운로드 결과를 확인할 수 없습니다.") from exc


def execute(url: str, start: float, root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[2] / ".artifacts" / "video-runs"
    directory = root.resolve() / uuid4().hex
    for name in ("source", "work", "output"):
        (directory / name).mkdir(parents=True, exist_ok=False)
    result = {
        "run_id": directory.name,
        "status": "failed",
        "stage": "input",
        "requested_start": start
        if isinstance(start, (int, float)) and float("-inf") < start < float("inf")
        else None,
        "requested_duration": 10,
        "tolerance_seconds": TOLERANCE,
        "checks": {},
        "tools": {},
        "result_path": str(directory / "result.json"),
    }
    begun = time.monotonic()
    published = False
    try:
        validate_start(start)
        kind, url = validate_url(url)
        result["source_type"] = kind
        result["stage"] = "tools"
        for tool in ("ffmpeg", "ffprobe"):
            result["tools"][tool] = run([executable(tool), "-version"], 10).splitlines()[0]
        if kind == "youtube":
            result["tools"]["deno"] = run([executable("deno"), "--version"], 10).splitlines()[0]
            result["tools"]["yt_dlp"] = yt_dlp_version
        result["stage"] = "download"
        source = download(url, directory / "source")
        result["source_path"] = str(source)
        original_hash = checksum(source)
        result["source_sha256"] = original_hash
        result["stage"] = "extract_and_validate"
        temporary = directory / "work" / "clip.mp4"
        info, checks = extract(source, temporary, start)
        checks["source_unchanged"] = original_hash == checksum(source)
        if not checks["source_unchanged"]:
            raise VideoError("OUTPUT_INVALID", "원본 파일 변경이 감지되었습니다.")
        final = directory / "output" / "clip.mp4"
        os.link(temporary, final)
        published = True
        temporary.unlink()
        result.update(
            status="succeeded",
            stage="complete",
            output_path=str(final),
            media=asdict(info),
            checks=checks,
        )
    except VideoError as exc:
        result["error"] = {"code": exc.code, "message": str(exc)}
    except OSError:
        result["error"] = {"code": "IO_FAILED", "message": "파일을 읽거나 저장하지 못했습니다."}
    finally:
        if result["status"] != "succeeded":
            (directory / "work" / "clip.mp4").unlink(missing_ok=True)
            if published:
                (directory / "output" / "clip.mp4").unlink(missing_ok=True)
        result["elapsed_seconds"] = round(time.monotonic() - begun, 3)
        (directory / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
    return result
