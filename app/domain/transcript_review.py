"""Deterministic triage, never an accuracy score or an automatic correction."""

import hashlib
import math

from app.domain.subtitles import build_subtitles, compact

VERSION = "transcript-review-v1"
FIELDS = ("avg_logprob", "no_speech_prob", "compression_ratio")


def quality(raw):
    result = {}
    if not isinstance(raw, dict):
        return result
    for key in FIELDS:
        value = raw.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            continue
        if key == "avg_logprob" and value > 0:
            continue
        if key == "no_speech_prob" and not 0 <= value <= 1:
            continue
        if key == "compression_ratio" and value < 0:
            continue
        result[key] = value
    return result


def inspect(segments):
    warnings = {}
    for cue in build_subtitles(segments)["cues"]:
        warnings.setdefault(cue["source_segment_id"], set()).update(cue["warnings"])
    rows = []
    previous = None
    for segment in segments:
        q = quality(segment.get("quality", {}))
        reasons = []
        low = q.get("avg_logprob", 0) < -1.0
        if low:
            reasons.append("LOW_CONFIDENCE")
        if low and q.get("no_speech_prob", 0) > 0.6:
            reasons.append("POSSIBLE_NON_SPEECH")
        if q.get("compression_ratio", 0) > 2.4:
            reasons.append("COMPRESSION_REPETITION")
        if previous is not None and compact(previous) == compact(segment["text"]):
            reasons.append("ADJACENT_REPETITION")
        previous = segment["text"]
        display = sorted(warnings.get(segment["id"], set()))
        rows.append(
            {
                **{key: segment[key] for key in ("id", "start_ms", "end_ms", "text")},
                "quality": q,
                "unavailable_metrics": [key for key in FIELDS if key not in q],
                "recognition_reasons": reasons,
                "display_reasons": display,
                "priority": "high"
                if low
                else "medium"
                if reasons
                or set(display) - {"WORD_TIMESTAMPS_UNAVAILABLE", "UNALIGNED_WORD_TIMESTAMPS"}
                else "none",
                "decision": None,
                "note": "",
                "revision": 0,
            }
        )
    order = {"high": 0, "medium": 1, "none": 2}
    rows.sort(key=lambda r: (order[r["priority"]], r["start_ms"], r["id"]))
    return {
        "policy_version": VERSION,
        "policy_status": "product_draft",
        "thresholds": {"avg_logprob": -1.0, "no_speech_prob": 0.6, "compression_ratio": 2.4},
        "total": len(rows),
        "flagged": sum(r["priority"] != "none" for r in rows),
        "quality_available": sum(bool(r["quality"]) for r in rows),
        "sample_seed": VERSION,
        "unflagged_sample_ids": [
            r["id"]
            for r in sorted(
                (r for r in rows if r["priority"] == "none"),
                key=lambda r: hashlib.sha256((VERSION + r["id"]).encode()).hexdigest(),
            )[:5]
        ],
        "segments": rows,
    }
