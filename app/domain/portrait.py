"""Fixed portrait proof-of-concept: explicit timing, plain captions, no ASR changes."""

from app.domain.video import VideoError

VERSION = "portrait-subtitle-sample-v1"
WIDTH, HEIGHT = 720, 1280


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


def ass_document(cues: list[dict], font_family: str) -> str:
    """Internal ASS only. Called with validated clip-relative cues and a known font family."""

    def timestamp(ms):
        seconds, centiseconds = divmod(ms // 10, 100)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"

    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {WIDTH}\nPlayResY: {HEIGHT}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_family},46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        "0,0,0,0,100,100,0,0,1,3,0,2,48,48,180,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    return header + "".join(
        f"Dialogue: 0,{timestamp(cue['start_ms'])},{timestamp(cue['end_ms'])},"
        "Default,,0,0,0,," + r"\N".join(cue["lines"]) + "\n"
        for cue in cues
    )
