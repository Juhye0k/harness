"""Offline proof-of-concept with synthetic pictures, a test tone, and fixture captions."""

import json
from pathlib import Path
from uuid import uuid4

from app.adapters.portrait import render_portrait
from app.adapters.process import executable, run
from app.domain.portrait import VERSION
from app.domain.subtitles import srt
from app.domain.video import VideoError

SOURCE_CUES = [
    {"start_ms": 2500, "end_ms": 3500, "lines": ["한국어 자막"]},
    {"start_ms": 4000, "end_ms": 5000, "lines": ["문장부호 확인!"]},
    {"start_ms": 6500, "end_ms": 7700, "lines": ["두 줄 자막", "표시 확인"]},
    {"start_ms": 9500, "end_ms": 10700, "lines": ["원본 음성 유지"]},
]


def execute(output_dir: Path | None = None) -> dict:
    directory = output_dir or Path(".artifacts/portrait-samples") / uuid4().hex
    if directory.exists() or directory.is_symlink():
        raise VideoError("OUTPUT_CONFLICT", "새 출력 폴더를 지정하세요. 기존 폴더는 보존합니다.")
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    result = {
        "status": "failed",
        "profile": VERSION,
        "input": "synthetic_video_and_test_tone",
        "start_ms": 2000,
        "duration_ms": 10000,
        "source_time_origin": "source_video",
        "subtitle_time_origin": "clip",
        "tools": {},
        "checks": {},
        "quality": "technical_sample_not_speech_alignment_evaluation",
    }
    try:
        for name in ("ffmpeg", "ffprobe"):
            result["tools"][name] = run([executable(name), "-version"], 10).splitlines()[0]
        source = directory / "source.mp4"
        run(
            [
                executable("ffmpeg"),
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=640x360:r=30:d=12",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=12",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(source),
            ],
            60,
        )
        rendered = render_portrait(source, directory / "clip.mp4", SOURCE_CUES, 2000, 10000)
        (directory / "subtitles.srt").write_text(srt(rendered), encoding="utf-8")
        run(
            [
                executable("ffmpeg"),
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-ss",
                "4.8",
                "-i",
                str(directory / "clip.mp4"),
                "-frames:v",
                "1",
                str(directory / "preview.png"),
            ],
            30,
        )
        result.update(rendered)
        result.update(
            status="succeeded",
            output_path=str(directory / "clip.mp4"),
            subtitle_path=str(directory / "subtitles.srt"),
            preview_path=str(directory / "preview.png"),
        )
    except VideoError as exc:
        result["error"] = {"code": exc.code, "message": str(exc)}
    except OSError:
        result["error"] = {"code": "IO_FAILED", "message": "샘플 파일을 저장하지 못했습니다."}
    if result["status"] != "succeeded":
        # Only remove artifacts created inside this newly created sample directory.
        for name in ("clip.mp4", "subtitles.srt", "preview.png"):
            (directory / name).unlink(missing_ok=True)
    result["result_path"] = str(directory / "result.json")
    (directory / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
