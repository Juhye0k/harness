"""Local portrait renderer for the fixed sample; no network or user-supplied filter code."""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from app.adapters.media import container, probe
from app.adapters.process import executable, run
from app.domain.portrait import HEIGHT, WIDTH, ass_document, clip_captions
from app.domain.video import VideoError, validate_output, validate_range


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def korean_font() -> tuple[Path, str]:
    candidates = [
        (Path("C:/Windows/Fonts/malgun.ttf"), "Malgun Gothic"),
        (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), "Noto Sans CJK KR"),
    ]
    for path, family in candidates:
        if path.is_file():
            return path, family
    raise VideoError(
        "FONT_MISSING", "한국어 폰트가 없습니다. Linux에서는 fonts-noto-cjk를 설치하세요."
    )


def render_portrait(
    source: Path, target: Path, cues: list[dict], start_ms: int, duration_ms: int
) -> dict:
    """Render validated source-relative cues and publish only after media checks."""
    if target.is_symlink():
        raise VideoError("OUTPUT_CONFLICT", "출력 경로로 심볼릭 링크를 사용할 수 없습니다.")
    source, target = source.resolve(), target.resolve()
    if source == target or target.exists():
        raise VideoError("OUTPUT_CONFLICT", "원본이나 기존 결과를 덮어쓸 수 없습니다.")
    subtitles = clip_captions(cues, start_ms, duration_ms)
    original = probe(source)
    validate_range(start_ms / 1000, original, duration_ms / 1000)
    font_path, family = korean_font()
    before = checksum(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Relative, fixed filter paths avoid quoting Windows drives, Unicode, and apostrophes.
    with tempfile.TemporaryDirectory(prefix=".portrait-", dir=target.parent) as directory:
        work = Path(directory).resolve()
        (work / "fonts").mkdir()
        shutil.copyfile(font_path, work / "fonts" / f"caption{font_path.suffix}")
        (work / "captions.ass").write_text(ass_document(subtitles, family), encoding="utf-8")
        output = work / "clip.mp4"
        run(
            [
                executable("ffmpeg"),
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-n",
                "-protocol_whitelist",
                "file,pipe",
                "-ss",
                str(start_ms / 1000),
                "-f",
                container(source, "INVALID_MEDIA"),
                "-i",
                str(source),
                "-t",
                str(duration_ms / 1000),
                "-map",
                "0:V:0",
                "-map",
                "0:a:0?",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-vf",
                "setpts=PTS-STARTPTS,"
                "scale=720:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                "setsar=1,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,"
                "ass=filename=captions.ass:fontsdir=fonts",
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
                str(output),
            ],
            120,
            cwd=work,
        )
        info = probe(output, output=True)
        checks = validate_output(info, original.has_audio, duration_ms / 1000)
        raw = run(
            [
                executable("ffprobe"),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,sample_aspect_ratio",
                "-of",
                "json",
                str(output),
            ],
            30,
        )
        try:
            stream = json.loads(raw)["streams"][0]
            checks["portrait_dimensions"] = (stream["width"], stream["height"]) == (WIDTH, HEIGHT)
            checks["square_pixels"] = stream["sample_aspect_ratio"] == "1:1"
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise VideoError("OUTPUT_INVALID", "출력 해상도를 확인할 수 없습니다.") from exc
        checks["source_unchanged"] = checksum(source) == before
        if not all(checks.values()):
            raise VideoError(
                "OUTPUT_INVALID", "해상도·화면 비율·원본 보존 검사를 통과하지 못했습니다."
            )
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
                str(output),
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
            os.link(output, target)
        except FileExistsError as exc:
            raise VideoError("OUTPUT_CONFLICT", "기존 결과를 덮어쓸 수 없습니다.") from exc
    return {
        "checks": checks,
        "font": {"family": family, "sha256": checksum(font_path)},
        "source_sha256": before,
        "output_sha256": checksum(target),
        "duration_seconds": info.duration,
        "width": WIDTH,
        "height": HEIGHT,
        "cues": subtitles,
    }
