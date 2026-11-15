"""FFmpeg extraction and FFprobe inspection of local files only."""

import json
import math
import os
import tempfile
from pathlib import Path

from app.adapters.process import executable, run
from app.domain.video import MediaInfo, VideoError, validate_output, validate_range


def container(path: Path, code: str) -> str:
    with path.open("rb") as stream:
        header = stream.read(12)
    if header[4:8] == b"ftyp":
        return "mov"
    if header[:4] == b"\x1aE\xdf\xa3":
        return "matroska"
    raise VideoError(code, "MP4 또는 WebM 영상 파일이 아닙니다.")


def probe(path: Path, *, output: bool = False) -> MediaInfo:
    code = "OUTPUT_INVALID" if output else "INVALID_MEDIA"
    if not path.is_file():
        raise VideoError(code, "검사할 영상 파일이 없습니다.")
    demuxer = container(path, code)
    try:
        raw = run(
            [
                executable("ffprobe"),
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_streams",
                "-show_format",
                "-f",
                demuxer,
                "-of",
                "json",
                str(path.resolve()),
            ],
            30,
        )
        metadata = json.loads(raw)
        streams = metadata["streams"]
        videos = [
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ]
        stream = videos[0]
        if "duration" in stream:
            duration = float(stream["duration"])
        else:
            hours, minutes, seconds = stream.get("tags", {})["DURATION"].split(":")
            duration = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Unknown video duration")
        total_duration = float(metadata["format"]["duration"])
        if not math.isfinite(total_duration) or total_duration <= 0:
            raise ValueError("Unknown container duration")
        return MediaInfo(
            duration,
            any(s.get("codec_type") == "audio" for s in streams),
            total_duration,
        )
    except VideoError as exc:
        if exc.code != "TOOL_FAILED":
            raise
        raise VideoError(code, "영상 파일을 읽을 수 없습니다.") from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise VideoError(code, "영상 트랙 또는 정확한 영상 길이를 확인할 수 없습니다.") from exc


def extract(
    source: Path, target: Path, start: float, duration: float = 10
) -> tuple[MediaInfo, dict]:
    source, target = source.resolve(), target.resolve()
    if source == target or target.exists():
        raise VideoError("OUTPUT_CONFLICT", "원본이나 기존 파일을 덮어쓸 수 없습니다.")
    info = probe(source)
    validate_range(start, info, duration)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(suffix=".mp4", prefix=".render-", dir=target.parent)
    os.close(fd)
    staging = Path(filename)
    try:
        run(
            [
                executable("ffmpeg"),
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-y",  # Only overwrite our exclusively-created staging file.
                "-protocol_whitelist",
                "file,pipe",
                "-f",
                container(source, "INVALID_MEDIA"),
                "-i",
                str(source),
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-map",
                "0:V:0",
                "-map",
                "0:a:0?",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-vf",
                "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(staging),
            ],
            120,
        )
        result = probe(staging, output=True)
        checks = validate_output(result, info.has_audio, duration)
        run(
            [
                executable("ffmpeg"),
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(staging),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-f",
                "null",
                "-",
            ],
            30,
        )
        checks["decodable"] = True
        try:
            os.link(staging, target)  # Atomic publication without replacing any existing path.
        except FileExistsError as exc:
            raise VideoError("OUTPUT_CONFLICT", "기존 파일을 덮어쓸 수 없습니다.") from exc
        return result, checks
    finally:
        staging.unlink(missing_ok=True)
