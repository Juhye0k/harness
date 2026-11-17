"""Short-form display policy; missing timing never becomes fabricated captions."""

from dataclasses import asdict

from app.domain.subtitles import SubtitlePolicy, compact, validate_words, word_units, wrap
from app.domain.video import VideoError

VERSION = "shorts-display-v1"
POLICY = SubtitlePolicy(
    max_line_chars=14,
    max_lines=2,
    max_duration_ms=1800,
    min_duration_ms=450,
    max_chars_per_second=15,
    pause_ms=300,
)


def partition(segment):
    validate_words(segment)
    tokens = word_units(segment)
    units = []
    for token in tokens:
        if units and not token["text"][:1].isspace():
            units[-1]["text"] += token["text"]
            units[-1]["end_ms"] = token["end_ms"]
        else:
            units.append(dict(token))
    # Complete partition only. Large two-line penalty prefers readable single lines.
    best = {len(units): (0, [])}
    for i in range(len(units) - 1, -1, -1):
        choices = []
        for j in range(i + 1, min(i + 3, len(units)) + 1):
            group = units[i:j]
            if j not in best or any(
                b["start_ms"] - a["end_ms"] >= POLICY.pause_ms
                for a, b in zip(group, group[1:], strict=False)
            ):
                continue
            text = "".join(u["text"] for u in group).strip()
            duration = group[-1]["end_ms"] - group[0]["start_ms"]
            lines = wrap(text, POLICY)
            if (
                not 450 <= duration <= 1800
                or len(text.split()) > 3
                or len(lines) > 2
                or any(len(line) > 14 for line in lines)
                or len(text) * 1000 > duration * 15
            ):
                continue
            cost = (len(lines) - 1) * 10000 + abs(duration - 900) / 1000 + 1
            # Prefer sentence-ending boundaries without making sub-minimum cues.
            if text.endswith((".", "!", "?", "。", "！", "？")):
                cost -= 0.2
            candidate = {
                "start_ms": group[0]["start_ms"],
                "end_ms": group[-1]["end_ms"],
                "text": text,
                "lines": lines,
                "eojeol_count": len(text.split()),
            }
            tail_cost, tail = best[j]
            choices.append((cost + tail_cost, [candidate, *tail]))
        if choices:
            best[i] = min(choices, key=lambda value: value[0])
    return best.get(0, (None, None))[1]


def build_shorts(segments, start_ms=None, end_ms=None):
    if (start_ms is None) != (end_ms is None) or (
        start_ms is not None and (start_ms < 0 or end_ms <= start_ms)
    ):
        raise ValueError("Both range bounds with 0 <= start < end are required")
    cues, blocked = [], []
    selected = [
        s
        for s in segments
        if start_ms is None or (s["end_ms"] > start_ms and s["start_ms"] < end_ms)
    ]
    for segment in selected:
        reason = "WORD_TIMING_UNVERIFIED"
        try:
            group = partition(segment) if "words" in segment else None
            if group is None and "words" in segment:
                reason = "NO_READABLE_PARTITION"
        except (VideoError, KeyError, TypeError, ValueError):
            group = None
        if group and cues and group[0]["start_ms"] < cues[-1]["end_ms"]:
            group, reason = None, "OVERLAPPING_CUES"
        if (
            group
            and start_ms is not None
            and any(
                c["start_ms"] < start_ms or c["end_ms"] > end_ms
                for c in group
                if c["end_ms"] > start_ms and c["start_ms"] < end_ms
            )
        ):
            group, reason = None, "RANGE_CUTS_CUE"
        if group is None:
            blocked.append(
                {**{k: segment[k] for k in ("id", "text", "start_ms", "end_ms")}, "reason": reason}
            )
            continue
        for cue in group:
            if start_ms is not None and not (
                start_ms <= cue["start_ms"] and cue["end_ms"] <= end_ms
            ):
                continue
            cues.append(
                {
                    **cue,
                    "id": f"cue{len(cues):04d}",
                    "source_segment_id": segment["id"],
                    "timing": "word",
                    "review_required": False,
                    "warnings": [],
                }
            )
    passed = not blocked and bool(cues)
    return {
        "version": VERSION,
        "profile": VERSION,
        "policy": {**asdict(POLICY), "max_eojeol": 3, "target_duration_ms": [600, 1200]},
        "policy_status": "product_draft",
        "alignment_version": "exact-timed-word-match-v1",
        "time_origin": "source_video",
        "cues": cues,
        "blocked_segments": blocked,
        "coverage_complete": not blocked,
        "quality_pass": passed,
        "review_required": not passed,
        "source_segments": len(selected),
        "ready_segments": len(selected) - len(blocked),
        "source_characters": sum(len(compact(s["text"])) for s in selected),
    }
