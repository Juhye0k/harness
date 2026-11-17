"""Manual captions share display limits but never claim automatic word alignment."""

import hashlib
import json

from app.domain.portrait import clip_captions
from app.domain.shorts_subtitles import POLICY
from app.domain.video import VideoError

PROFILE = "portrait-edited-v1"


def validate_cues(cues, segments, start_ms, end_ms, reviewed):
    # Also validates bounds, ordering, plain text and the renderer's safe syntax.
    clip_captions(cues, start_ms, end_ms - start_ms)
    known = {s["id"] for s in segments}
    seen, result = set(), []
    for cue in cues:
        source_id = cue.get("source_segment_id")
        duration = cue["end_ms"] - cue["start_ms"]
        text = " ".join(cue["lines"])
        if (
            not isinstance(source_id, str)
            or source_id not in known
            or not POLICY.min_duration_ms <= duration <= POLICY.max_duration_ms
            or len(text.split()) > 3
            or len(text) * 1000 > duration * POLICY.max_chars_per_second
        ):
            raise VideoError(
                "SUBTITLE_INVALID",
                "자막은 원 구간에 연결된 1~3어절·0.45~1.8초·15자/초 이하여야 합니다.",
            )
        seen.add(source_id)
        result.append({k: cue[k] for k in ("source_segment_id", "start_ms", "end_ms", "lines")})
    if reviewed and seen != known:
        raise VideoError(
            "SUBTITLE_INCOMPLETE", "누락한 원 구간이 있습니다. 모든 원 구간의 자막을 확인하세요."
        )
    return result


def content_hash(cues, source_version, reviewed):
    payload = {
        "profile": PROFILE,
        "source_version": source_version,
        "reviewed": reviewed,
        "cues": cues,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
