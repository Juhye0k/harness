"""Reuse YouTube word onsets as proposed DISPLAY intervals, not verified speech ends."""

from bisect import bisect_left, bisect_right

from app.domain.shorts_subtitles import POLICY
from app.domain.subtitles import wrap


def youtube_onsets(raw, duration_ms):
    if type(duration_ms) is not int or not 0 < duration_ms <= 1_200_000:
        raise ValueError("Invalid original duration")
    events = raw.get("events")
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError("Invalid caption events")
    words = []
    for event in events:
        for segment in event.get("segs", []):
            text = segment.get("utf8", "")
            if not isinstance(text, str) or len(text) > 500:
                raise ValueError("Invalid caption text")
            if not text.strip():
                continue  # Rolling-window newline events are not repeated spoken words.
            base, offset = event.get("tStartMs"), segment.get("tOffsetMs", 0)
            if (
                type(base) is not int
                or type(offset) is not int
                or offset < 0
                or not 0 <= base + offset < duration_ms
                or any(char in "{}\\" or ord(char) < 32 for char in text.strip())
            ):
                raise ValueError("Invalid word onset")
            start = base + offset
            if words and start < words[-1]["start_ms"]:
                raise ValueError("Nonmonotonic word onsets")
            if words and start == words[-1]["start_ms"]:
                # Provider resolution can assign two real words the same onset.
                # Keep both as one timed unit; do not deduplicate or invent offsets.
                words[-1]["text"] += " " + text.strip()
                continue
            words.append({"text": text.strip(), "start_ms": start})
    return words


def propose(words, segments, start_ms, end_ms, *, screen_changes=(), snap_ms=0):
    if not words or not segments or not 0 <= start_ms < end_ms:
        raise ValueError("Missing words, source links, or valid range")
    if start_ms <= words[-1]["start_ms"] < end_ms:
        return {
            "status": "UNRESOLVED_FINAL_WORD",
            "cues": [],
            "unresolved_words": [words[-1]],
            "cut_words": [],
            "words_dropped_for_readability": 0,
        }
    selected, cut = [], []
    for word, following in zip(words, words[1:], strict=False):
        if word["start_ms"] >= end_ms or following["start_ms"] <= start_ms:
            continue
        if word["start_ms"] < start_ms or following["start_ms"] > end_ms:
            cut.append({**word, "next_onset_ms": following["start_ms"]})
            continue
        selected.append({**word, "end_ms": following["start_ms"]})
    if not selected:
        raise ValueError("No complete onset intervals inside candidate")
    onsets = [word["start_ms"] for word in selected]
    boundaries = set()
    for change in screen_changes:
        position = bisect_left(onsets, change)
        # Reject unsupported transitions. Ties favor the earlier word onset.
        nearest = min(onsets[max(0, position - 1) : position + 1], key=lambda t: abs(t - change))
        if abs(nearest - change) <= snap_ms:
            boundaries.add(nearest)
    boundaries = sorted(boundaries)
    # Complete partition: never hide a word just to improve readability metrics.
    best = {len(selected): (0, [])}
    for index in range(len(selected) - 1, -1, -1):
        choices = []
        for stop in range(index + 1, min(index + 3, len(selected)) + 1):
            if stop not in best:
                continue
            group = selected[index:stop]
            text = " ".join(word["text"] for word in group)
            begin, end = group[0]["start_ms"], group[-1]["end_ms"]
            lines = wrap(text, POLICY)
            duration = end - begin
            if (
                not 450 <= duration <= 1800
                or not 1 <= len(text.split()) <= 3
                or len(lines) > 2
                or any(len(line) > 14 for line in lines)
                or len(text) * 1000 > duration * 15
            ):
                continue
            owner = max(
                segments, key=lambda s: max(0, min(end, s["end_ms"]) - max(begin, s["start_ms"]))
            )
            if min(end, owner["end_ms"]) <= max(begin, owner["start_ms"]):
                continue
            cue = {
                "source_segment_id": owner["id"],
                "start_ms": begin,
                "end_ms": end,
                "lines": lines,
            }
            cost, tail = best[stop]
            crossed = bisect_left(boundaries, end) - bisect_right(boundaries, begin)
            choices.append(
                (
                    cost + 1 + abs(duration - 900) / 1000 + (len(lines) - 1) * 10000 + 2 * crossed,
                    [cue, *tail],
                )
            )
        if choices:
            best[index] = min(choices, key=lambda row: row[0])
    if 0 not in best:
        return {
            "status": "NO_COMPLETE_READABLE_PARTITION",
            "cues": [],
            "cut_words": cut,
            "selected_words": len(selected),
            "words_dropped_for_readability": 0,
        }
    return {
        "status": "draft",
        "cues": best[0][1],
        "cut_words": cut,
        "selected_words": len(selected),
        "words_dropped_for_readability": 0,
        "timing_source": "youtube_word_onsets_with_next_onset_display_end",
        "snapped_screen_boundaries_ms": boundaries,
        "speech_end_verified": False,
        "human_reviewed": False,
    }
