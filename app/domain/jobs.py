"""Business failures and public job-result boundary."""

from pathlib import Path


class JobError(Exception):
    def __init__(self, code: str, message: str, status_code: int, job_id=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.job_id = job_id


def output_file(root: Path, relative: str | None) -> Path:
    if not relative or Path(relative).is_absolute():
        raise JobError("RESULT_UNAVAILABLE", "결과 파일을 사용할 수 없습니다.", 410)
    base = root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise JobError("RESULT_UNAVAILABLE", "결과 파일을 사용할 수 없습니다.", 410)
    return path


def public_result(result: dict) -> dict:
    """Select known fields; never return CLI paths, URLs or arbitrary messages."""
    media = result.get("media", {})
    checks = result.get("checks", {})
    return {
        "media": {
            k: media[k] for k in ("duration", "has_audio", "container_duration") if k in media
        },
        "checks": {
            k: checks[k]
            for k in (
                "duration",
                "video_track",
                "audio_preserved",
                "decodable",
                "source_unchanged",
            )
            if k in checks
        },
    }
