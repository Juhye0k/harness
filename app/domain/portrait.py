"""Versioned portrait layout and explicit caption timing."""

from hashlib import sha256
from json import dumps

from app.domain.video import VideoError

VERSION = "portrait-subtitle-sample-v1"
LEGACY_EDITED_PROFILE = "portrait-edited-v1"
EDITED_PROFILE = "portrait-edited-v2"
WIDTH, HEIGHT = 720, 1280
CAPTION_BAND_HEIGHT = 192
MAX_VISIBLE_SPANS = 200


def clip_captions(cues: list[dict], start_ms: int, duration_ms: int) -> list[dict]:
    """Convert already selected source cues; never trim a cue or invent word timing."""
    if (
        type(start_ms) is not int
        or type(duration_ms) is not int
        or start_ms < 0
        or not 0 < duration_ms <= 60000
    ):
        raise VideoError("INVALID_RANGE", "정수 밀리초 구간과 60초 이하 길이가 필요합니다.")
    if not isinstance(cues, list) or not cues or len(cues) > 200:
        raise VideoError("SUBTITLE_INVALID", "확인된 자막이 필요합니다.")
    converted = []
    previous = start_ms
    for cue in cues:
        if not isinstance(cue, dict):
            raise VideoError("SUBTITLE_INVALID", "자막 형식이 잘못되었습니다.")
        begin, end, lines = cue.get("start_ms"), cue.get("end_ms"), cue.get("lines")
        if (
            type(begin) is not int
            or type(end) is not int
            or begin < previous
            or end <= begin
            or end > start_ms + duration_ms
        ):
            raise VideoError("SUBTITLE_INVALID", "자막이 겹치거나 선택 구간을 벗어납니다.")
        # This spike accepts plain, short fixture captions only. Do not accept ASS commands.
        if (
            not isinstance(lines, list)
            or not 1 <= len(lines) <= 2
            or any(
                not isinstance(line, str)
                or not line.strip()
                or len(line) > 14
                or any(char in "{}\\" or ord(char) < 32 for char in line)
                for line in lines
            )
        ):
            raise VideoError("SUBTITLE_INVALID", "자막은 제어문자 없는 14자·2줄 이하여야 합니다.")
        converted.append(
            {"start_ms": begin - start_ms, "end_ms": end - start_ms, "lines": lines[:]}
        )
        previous = end
    return converted


def visible_spans(spans: list[dict], start_ms: int, end_ms: int) -> list[dict]:
    """Validate source-relative positive observations and merge adjacent ranges."""
    if len(spans) > MAX_VISIBLE_SPANS:
        raise VideoError("SOURCE_CAPTIONS_INVALID", "원본 자막 관측 구간은 최대 200개입니다.")
    merged = []
    previous = start_ms
    for span in spans:
        begin, end = span.get("start_ms"), span.get("end_ms")
        if (
            type(begin) is not int
            or type(end) is not int
            or begin < previous
            or end <= begin
            or end > end_ms
        ):
            raise VideoError(
                "SOURCE_CAPTIONS_INVALID",
                "원본 자막 관측 구간은 겹치지 않고 후보 안에 있어야 합니다.",
            )
        if merged and begin == previous:
            merged[-1]["end_ms"] = end
        else:
            merged.append({"start_ms": begin, "end_ms": end})
        previous = end
    return merged


def render_input_hash(profile: str, source_sha256: str, spans: list[dict]) -> str:
    payload = {"profile": profile, "source_sha256": source_sha256, "visible_spans": spans}
    return sha256(dumps(payload, sort_keys=True).encode()).hexdigest()


def unsuppressed_captions(cues: list[dict], spans: list[dict], start_ms: int) -> list[dict]:
    """Keep cue portions outside confirmed spans, at ASS's centisecond resolution."""
    suppressed_times = []
    for span in spans:
        begin = ((span["start_ms"] - start_ms + 9) // 10) * 10
        end = ((span["end_ms"] - start_ms) // 10) * 10
        if begin < end:
            suppressed_times.append((begin, end))
    if not suppressed_times:
        return cues
    visible = []
    for cue in cues:
        cursor = (cue["start_ms"] // 10) * 10
        last = (cue["end_ms"] // 10) * 10
        for begin, end in suppressed_times:
            if begin >= last:
                break
            if end <= cursor:
                continue
            if begin > cursor:
                visible.append({**cue, "start_ms": cursor, "end_ms": begin})
            cursor = end
        if cursor < last:
            visible.append({**cue, "start_ms": cursor, "end_ms": last})
    return visible


def ass_document(cues: list[dict], font_family: str, *, caption_band: bool = False) -> str:
    """Internal ASS only. Called with validated clip-relative cues and a known font family."""

    def timestamp(ms):
        seconds, centiseconds = divmod(ms // 10, 100)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"

    play_height = CAPTION_BAND_HEIGHT if caption_band else HEIGHT
    alignment, margin_v = (8, 22) if caption_band else (2, 180)
    # Fit all 14 characters inside the horizontal safe area, including wide Korean glyphs.
    font_size = 42 if caption_band else 46
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {WIDTH}\nPlayResY: {play_height}\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_family},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,3,0,{alignment},48,48,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    return header + "".join(
        f"Dialogue: 0,{timestamp(cue['start_ms'])},{timestamp(cue['end_ms'])},"
        "Default,,0,0,0,," + r"\N".join(cue["lines"]) + "\n"
        for cue in cues
    )
