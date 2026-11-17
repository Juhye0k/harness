"""Display-only subtitles. Never invent word timing or modify the source transcript."""

import re
from dataclasses import asdict, dataclass

from app.domain.video import VideoError

VERSION = "ko-display-v1"


@dataclass(frozen=True)
class SubtitlePolicy:
    # Product draft, not a validated accessibility or broadcaster specification.
    max_line_chars: int = 20
    max_lines: int = 2
    max_duration_ms: int = 6000
    min_duration_ms: int = 800
    max_chars_per_second: int = 15
    pause_ms: int = 700


POLICY = SubtitlePolicy()
SENTENCE_END = re.compile(r"""[.!?…。！？][”’"'）)\]]*$""")


def compact(text):
    return "".join(text.split())


def invalid():
    return VideoError(
        "MODEL_RESPONSE_INVALID", "단어 전사가 원문 또는 시간 계약과 일치하지 않습니다."
    )


def validate_words(segment):
    """Require exact character coverage in order, allowing whitespace differences only."""
    words = segment["words"]
    if not isinstance(words, list) or not words or len(words) > 60000:
        raise invalid()
    last = segment["start_ms"]
    pieces = []
    for word in words:
        if not isinstance(word, dict) or not isinstance(word.get("text"), str):
            raise invalid()
        start, end = word.get("start_ms"), word.get("end_ms")
        if (
            type(start) is not int
            or type(end) is not int
            or start < last
            or end <= start
            or end > segment["end_ms"]
            or not compact(word["text"])
        ):
            raise invalid()
        pieces.append(compact(word["text"]))
        last = end
    if "".join(pieces) != compact(segment["text"]):
        raise invalid()
    return words


def word_units(segment):
    """Slice source characters at verified word boundaries; preserve punctuation and spaces."""
    words = validate_words(segment)
    text = " ".join(segment["text"].split())
    positions = [i for i, char in enumerate(text) if not char.isspace()]
    offset = previous = 0
    result = []
    for word in words:
        offset += len(compact(word["text"]))
        boundary = positions[offset - 1] + 1
        result.append({**word, "text": text[previous:boundary]})
        previous = boundary
    return result


def wrap(text, policy):
    lines = []
    for part in text.split():
        if lines and len(lines[-1]) + 1 + len(part) <= policy.max_line_chars:
            lines[-1] += " " + part
        else:
            lines.append(part)
    return lines


def build_subtitles(segments, policy=POLICY):
    cues = []

    def emit(segment, units, timing):
        text = "".join(unit["text"] for unit in units).strip()
        start, end = units[0]["start_ms"], units[-1]["end_ms"]
        lines = wrap(text, policy)
        duration = end - start
        warnings = []
        if timing == "segment":
            warnings.append("WORD_TIMESTAMPS_UNAVAILABLE")
            if segment.get("word_timestamps_issue") == "UNALIGNED_WORD_TIMESTAMPS":
                warnings.append("UNALIGNED_WORD_TIMESTAMPS")
        if len(lines) > policy.max_lines or any(
            len(line) > policy.max_line_chars for line in lines
        ):
            warnings.append("TEXT_LIMIT")
        if duration > policy.max_duration_ms:
            warnings.append("DURATION_LIMIT")
        if duration < policy.min_duration_ms:
            warnings.append("SHORT_DURATION")
        if len(text) * 1000 > duration * policy.max_chars_per_second:
            warnings.append("READING_SPEED")
        if cues and start < cues[-1]["end_ms"]:
            warnings.append("OVERLAPPING_CUES")
        cues.append(
            {
                "id": f"cue{len(cues):04d}",
                "source_segment_id": segment["id"],
                "start_ms": start,
                "end_ms": end,
                "text": text,
                "lines": lines,
                "timing": timing,
                "review_required": bool(warnings),
                "warnings": warnings,
            }
        )

    for segment in segments:
        if "words" not in segment:
            # Old and other-provider transcripts retain their exact segment boundaries.
            emit(segment, [segment], "segment")
            continue
        units = word_units(segment)
        group = []
        for unit in units:
            proposed = group + [unit]
            text = "".join(word["text"] for word in proposed).strip()
            if group and (
                unit["end_ms"] - group[0]["start_ms"] > policy.max_duration_ms
                or len(wrap(text, policy)) > policy.max_lines
                or any(len(line) > policy.max_line_chars for line in wrap(text, policy))
                or unit["start_ms"] - group[-1]["end_ms"] >= policy.pause_ms
                or SENTENCE_END.search(group[-1]["text"].rstrip())
            ):
                emit(segment, group, "word")
                group = []
            group.append(unit)
        if group:
            emit(segment, group, "word")
    return {
        "version": VERSION,
        "policy": asdict(policy),
        "policy_status": "product_draft",
        "time_origin": "source_video",
        "review_required": any(c["review_required"] for c in cues),
        "cues": cues,
    }


def srt(subtitles):
    def timestamp(ms):
        seconds, milliseconds = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    return "".join(
        f"{index}\n{timestamp(cue['start_ms'])} --> {timestamp(cue['end_ms'])}\n"
        + "\n".join(cue["lines"])
        + "\n\n"
        for index, cue in enumerate(subtitles["cues"], 1)
    )
