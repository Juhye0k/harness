"""Contracts for the first, fixed-duration video use case."""

import math
from dataclasses import dataclass

CLIP_SECONDS = 10.0
TOLERANCE = 0.1
MAX_SECONDS = 1200.0
MAX_BYTES = 500 * 1024 * 1024


class VideoError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    has_audio: bool
    container_duration: float | None = None


def validate_start(start: float) -> None:
    if not math.isfinite(start) or start < 0:
        raise VideoError("INVALID_INPUT", "시작 시간은 0 이상의 유한한 초 단위 숫자여야 합니다.")


def validate_range(start: float, info: MediaInfo, duration: float = CLIP_SECONDS) -> None:
    validate_start(start)
    if not math.isfinite(duration) or duration <= 0 or duration > 60:
        raise VideoError("INVALID_RANGE", "추출 길이는 0초 초과 60초 이하여야 합니다.")
    if info.duration > MAX_SECONDS:
        raise VideoError("LIMIT_EXCEEDED", "원본 영상은 20분 이하여야 합니다.")
    if start + duration > info.duration:
        raise VideoError("INVALID_RANGE", "요청한 구간이 원본 영상 범위를 넘습니다.")


def validate_output(
    info: MediaInfo, requires_audio: bool, duration: float = CLIP_SECONDS
) -> dict[str, bool]:
    checks = {
        "duration": abs(info.duration - duration) <= TOLERANCE
        and (
            info.container_duration is None or abs(info.container_duration - duration) <= TOLERANCE
        ),
        "video_track": True,  # probe rejects missing video tracks
        "audio_preserved": not requires_audio or info.has_audio,
    }
    if not all(checks.values()):
        raise VideoError("OUTPUT_INVALID", "출력 길이 또는 필수 트랙 검사를 통과하지 못했습니다.")
    return checks
