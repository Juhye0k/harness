"""Upload approval and immutable output identity; no provider calls."""

import hashlib
import re
from pathlib import Path


class SnsError(Exception):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def output_version(path: Path) -> str:
    # This MVP accepts small exports only; bound preview hashing and upload size.
    if not 0 < path.stat().st_size <= 256 * 1024 * 1024:
        raise SnsError("OUTPUT_TOO_LARGE", "출력은 0바이트 초과, 256MiB 이하여야 합니다.")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_title(title: str) -> str:
    if not title.strip() or len(title) > 100 or re.search(r"[<>\x00-\x1f\x7f]", title):
        raise SnsError("INVALID_TITLE", "제목은 1~100자이며 꺾쇠·제어 문자를 쓸 수 없습니다.", 422)
    return title


def approval_values(upload):
    return {
        "account_id": str(upload.account_id),
        "account_version": upload.account_version,
        "job_id": str(upload.job_id),
        "output_version": upload.output_version,
        "title": upload.title,
        "privacy": upload.privacy,
        "made_for_kids": upload.made_for_kids,
    }
