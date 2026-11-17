"""Recover exact word spans independently. Never edit source text or invent timestamps."""

import math
from bisect import bisect_left, bisect_right
from copy import deepcopy

from app.domain.subtitles import compact, validate_words
from app.domain.video import VideoError

VERSION = "exact-timed-word-match-v1"


def recover(segments, raw_words, *, boundary_tolerance_ms=0, duration_ms=None):
    if boundary_tolerance_ms not in (0, 150, 250):
        raise ValueError("Only strict alignment or bounded offline previews are supported")
    result = deepcopy(segments)
    diagnostics = []
    words, valid = [], True
    try:
        if not isinstance(raw_words, list) or len(raw_words) > 60000:
            raise ValueError()
        for raw in raw_words:
            start, end, text = raw["start"], raw["end"], raw["word"]
            if (
                any(type(t) not in (int, float) or not math.isfinite(t) for t in (start, end))
                or not isinstance(text, str)
                or not compact(text)
            ):
                raise ValueError()
            start, end = round(start * 1000), round(end * 1000)
            if start < 0 or end <= start or end > 1_200_000:
                raise ValueError()
            words.append({"text": text, "start_ms": start, "end_ms": end})
    except (KeyError, TypeError, ValueError, OverflowError):
        valid = False
        words = []
    # Index by time only for lookup. Selected words retain provider order and must
    # independently pass monotonic-time validation; never sort a phrase to fit it.
    ordered = sorted((word["start_ms"], index) for index, word in enumerate(words))
    starts = [start for start, _ in ordered]
    used, last_end = set(), -1
    for segment in result:
        segment.pop("words", None)
        low = max(0, segment["start_ms"] - boundary_tolerance_ms)
        high = segment["end_ms"] + boundary_tolerance_ms
        if duration_ms is not None:
            high = min(high, duration_ms)
        left, right = bisect_left(starts, low), bisect_right(starts, high)
        possible = sorted(
            index for _, index in ordered[left:right] if words[index]["end_ms"] <= high
        )
        matches = []
        target = compact(segment["text"])
        if valid and target:
            if boundary_tolerance_ms == 0:
                if (
                    possible
                    and possible == list(range(possible[0], possible[-1] + 1))
                    and "".join(compact(words[i]["text"]) for i in possible) == target
                ):
                    matches = [possible]
            else:
                # Experimental preview only: no interpolation, clipping, or word edits.
                for start_index in possible:
                    covered, group = "", []
                    for index in range(start_index, len(words)):
                        if words[index]["start_ms"] < low or words[index]["end_ms"] > high:
                            break
                        covered += compact(words[index]["text"])
                        group.append(index)
                        if not target.startswith(covered):
                            break
                        if covered == target:
                            matches.append(group)
                            break
        accepted = []
        for indices in matches:
            if not indices or used.intersection(indices):
                continue
            selected = [words[i] for i in indices]
            if selected[0]["start_ms"] < last_end:
                continue
            try:
                validate_words({**segment, "start_ms": low, "end_ms": high, "words": selected})
            except VideoError:
                continue
            accepted.append(indices)
        reason = "INVALID_WORD_DATA" if not valid else "NO_EXACT_TIME_MATCH"
        if len(accepted) == 1:
            indices = accepted[0]
            segment["words"] = [deepcopy(words[i]) for i in indices]
            segment.pop("word_timestamps_issue", None)
            used.update(indices)
            last_end = words[indices[-1]]["end_ms"]
            reason = "EXACT_MATCH"
        else:
            segment["word_timestamps_issue"] = "UNALIGNED_WORD_TIMESTAMPS"
            if len(accepted) > 1:
                reason = "AMBIGUOUS_MATCH"
        diagnostics.append({"segment_id": segment["id"], "reason": reason})
    matched = sum("words" in segment for segment in result)
    return result, {
        "version": VERSION,
        "boundary_tolerance_ms": boundary_tolerance_ms,
        "experimental": boundary_tolerance_ms != 0,
        "total_segments": len(result),
        "matched_segments": matched,
        "fallback_segments": len(result) - matched,
        "unused_words": len(words) - len(used),
        "segments": diagnostics,
    }
