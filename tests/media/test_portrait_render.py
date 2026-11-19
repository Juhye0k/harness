"""Real portrait rendering, caption appearance, trim position, and audio-track checks."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.adapters.media import probe
from app.adapters.portrait import korean_font, render_portrait
from app.adapters.process import executable, run
from app.domain.portrait import EDITED_PROFILE, ass_document
from app.domain.video import VideoError
from app.services.portrait_sample import execute
from app.services.video import checksum

EDITED_LINES = ["가나다라마바사아자차카타파하", "하파타카차자아사바마라다나가"]
EDITED_CAPTION_CROP = "crop=720:192:0:746"


def pixels(path, second, crop):
    return subprocess.check_output(
        [
            executable("ffmpeg"),
            "-v",
            "error",
            "-ss",
            str(second),
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            crop,
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        timeout=15,
    )


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    # Both Unicode and filter syntax characters must work in directory names.
    directory = tmp_path_factory.mktemp("한글 렌더's [sample]")
    source = directory / "source.mp4"
    run(
        [
            executable("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=30:d=2",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=30:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a:0",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        30,
    )
    before = checksum(source)
    output = directory / "clip.mp4"
    result = render_portrait(
        source,
        output,
        [{"start_ms": 1500, "end_ms": 2500, "lines": ["한국어 자막", "두 줄 확인!"]}],
        1000,
        3000,
    )
    return source, output, before, result


def test_real_portrait_is_valid_and_preserves_original(rendered):
    source, output, before, result = rendered
    assert all(result["checks"].values())
    assert (result["width"], result["height"]) == (720, 1280)
    assert abs(probe(output).duration - 3) <= 0.1
    assert probe(output).has_audio
    assert checksum(source) == before == result["source_sha256"]
    assert result["cues"][0]["start_ms"] == 500
    assert result["cues"][0]["end_ms"] == 1500
    assert not list(output.parent.glob(".portrait-*"))


def test_caption_pixels_follow_clip_times_and_two_lines(rendered):
    _, output, _, _ = rendered
    # The area beneath the preserved source picture is otherwise black.
    crop = "crop=720:320:0:900"
    before, during, after = [pixels(output, t, crop) for t in (0.2, 1, 1.8)]
    assert max(before) < 12
    assert max(after) < 12
    bright_rows = [
        row
        for row in range(320)
        if sum(value > 180 for value in during[row * 720 * 3 : (row + 1) * 720 * 3]) > 30
    ]
    assert len(bright_rows) > 30
    # Two independent text bands, separated by the inter-line gap.
    bands = 1 + sum(b - a > 1 for a, b in zip(bright_rows, bright_rows[1:], strict=False))
    assert bands >= 2


def test_source_content_starts_at_requested_offset_and_padding_is_black(rendered):
    _, output, _, _ = rendered
    for time, dominant in ((0.5, 0), (1.5, 2)):
        frame = pixels(output, time, "crop=100:100:300:550,scale=1:1")
        assert frame[dominant] > 200
        assert frame[2 if dominant == 0 else 0] < 30
    assert max(pixels(output, 1, "crop=720:100:0:0")) < 12


def test_invalid_source_range_does_not_create_output(rendered, tmp_path):
    source, _, before, _ = rendered
    output = tmp_path / "invalid.mp4"
    with pytest.raises(VideoError) as failure:
        render_portrait(
            source, output, [{"start_ms": 4000, "end_ms": 4500, "lines": ["확인"]}], 3500, 1000
        )
    assert failure.value.code == "INVALID_RANGE"
    assert checksum(source) == before
    assert not output.exists()


def test_offline_sample_has_matching_srt_and_preview(tmp_path):
    result = execute(tmp_path / "sample")
    assert result["status"] == "succeeded", result
    assert all(result["checks"].values())
    assert result["subtitle_time_origin"] == "clip"
    subtitle = Path(result["subtitle_path"]).read_text(encoding="utf-8")
    assert "00:00:00,500 --> 00:00:01,500" in subtitle
    assert "두 줄 자막\n표시 확인" in subtitle
    assert Path(result["preview_path"]).read_bytes().startswith(b"\x89PNG")
    assert json.loads(Path(result["result_path"]).read_text(encoding="utf-8")) == result


@pytest.fixture(scope="module")
def edited_layout(tmp_path_factory):
    directory = tmp_path_factory.mktemp("edited-layout")
    source = directory / "source.mp4"
    _, family = korean_font()
    (directory / "source.ass").write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 180\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, Alignment, MarginV\n"
        f"Style: Default,{family},18,&H00FFFFFF,&H00000000,2,12\n"
        "[Events]\nFormat: Layer, Start, End, Style, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.20,Default,원본 글자\n",
        encoding="utf-8",
    )
    run(
        [
            executable("ffmpeg"),
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x506176:s=320x180:r=30:d=4.1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4.1",
            "-vf",
            "drawbox=0:0:32:180:0x21836a:t=fill,"
            "drawbox=288:0:32:180:0xb65849:t=fill,"
            "drawbox=232:18:48:32:0x4d96d8:t=fill,ass=source.ass",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        30,
        cwd=directory,
    )
    cues = [
        {
            "start_ms": 1300,
            "end_ms": 2800,
            "lines": EDITED_LINES,
        }
    ]
    observed, unknown = directory / "observed.mp4", directory / "unknown.mp4"
    before = checksum(source)
    rendered = render_portrait(
        source,
        observed,
        cues,
        1000,
        3000,
        profile=EDITED_PROFILE,
        source_caption_spans=[{"start_ms": 1000, "end_ms": 2200}],
    )
    render_portrait(source, unknown, cues, 1000, 3000, profile=EDITED_PROFILE)
    return source, observed, unknown, before, rendered


def bright_points(frame, width):
    return [
        ((i // 3) % width, (i // 3) // width)
        for i in range(0, len(frame), 3)
        if min(frame[i : i + 3]) > 180
    ]


def test_edited_layout_keeps_visible_source_and_fills_black_padding(edited_layout):
    source, observed, _, before, result = edited_layout
    assert all(result["checks"].values())
    assert (result["width"], result["height"]) == (720, 1280)
    assert abs(probe(observed).duration - 3) <= 0.1 and probe(observed).has_audio
    assert checksum(source) == before == result["source_sha256"]
    assert result["cues"][0]["start_ms"] == 300
    assert result["cues"][0]["end_ms"] == 1800

    left, right, inset, middle, top, bottom = [
        pixels(observed, 0.8, f"crop=4:4:{x}:{y},scale=1:1")
        for x, y in ((6, 348), (710, 738), (540, 390), (168, 700), (6, 6), (6, 1270))
    ]
    assert left[1] > left[0] + 30
    assert right[0] > right[1] + 30
    assert inset[2] > inset[0] + 60
    assert middle[2] > middle[0] + 20
    assert min(top) > 16 and min(bottom) > 16
    assert max(top) < 100 and max(bottom) < 100


def test_edited_layout_uses_original_caption_then_replaces_it_in_its_absence(edited_layout):
    _, observed, unknown, _, _ = edited_layout
    original_crop = "crop=320:68:200:674"
    before_gap, inside_gap, after_cue = 0.8, 1.5, 2.2
    assert len(bright_points(pixels(observed, before_gap, original_crop), 320)) > 100
    assert not bright_points(pixels(observed, inside_gap, original_crop), 320)
    assert not bright_points(pixels(observed, before_gap, EDITED_CAPTION_CROP), 720)
    assert not bright_points(pixels(observed, after_cue, EDITED_CAPTION_CROP), 720)
    assert len(bright_points(pixels(observed, inside_gap, EDITED_CAPTION_CROP), 720)) > 500
    # Unobserved intervals retain the edited caption even if an original happens to exist.
    assert len(bright_points(pixels(unknown, before_gap, EDITED_CAPTION_CROP), 720)) > 500


def unclipped_caption_points(directory):
    font_path, family = korean_font()
    fonts = directory / "fonts"
    fonts.mkdir()
    shutil.copyfile(font_path, fonts / f"caption{font_path.suffix}")
    document = ass_document(
        [{"start_ms": 0, "end_ms": 1000, "lines": EDITED_LINES}], family, caption_band=True
    )
    # Expand both script and frame at 1:1 scale. The top-center anchor moves 360 px
    # right and stays at the same height. No portrait filter can crop the reference.
    (directory / "reference.ass").write_text(
        document.replace("PlayResX: 720\nPlayResY: 192\n", "PlayResX: 1440\nPlayResY: 384\n"),
        encoding="utf-8",
    )
    frame = subprocess.check_output(
        [
            executable("ffmpeg"),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x24333b:s=1440x384",
            "-vf",
            "ass=reference.ass:fontsdir=fonts",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        cwd=directory,
        timeout=15,
    )
    return {(x - 360, y) for x, y in bright_points(frame, 1440)}


def test_edited_layout_centers_two_readable_lines_without_clipping(edited_layout, tmp_path):
    _, observed, _, _, _ = edited_layout
    points = set(bright_points(pixels(observed, 1.5, EDITED_CAPTION_CROP), 720))
    reference = unclipped_caption_points(tmp_path)
    rows = sorted({y for _, y in points})
    line_breaks = [b for a, b in zip(rows, rows[1:], strict=False) if b - a > 2]
    assert len(line_breaks) == 1, "expected two visible lines with a gap"
    second_line = line_breaks[0]
    for first in (True, False):
        actual_line = {(x, y) for x, y in points if (y < second_line) == first}
        reference_line = {(x, y) for x, y in reference if (y < second_line) == first}
        xs, ys = zip(*actual_line, strict=True)
        assert min(xs) >= 48 and max(xs) < 720 - 48
        # The ink may have asymmetric side bearings even with a centered text advance.
        assert (min(xs) + max(xs)) / 2 == pytest.approx(359.5, abs=5)
        assert min(ys) >= 15 and max(ys) < 135
        assert max(ys) - min(ys) + 1 >= 21  # At least half the 42-unit ASS size is visible.
        # Thresholded edge pixels can change after H.264 encoding. Compare the whole
        # line so a lost glyph or stroke cannot pass on bounding rectangle alone.
        assert len(actual_line & reference_line) / len(actual_line | reference_line) >= 0.97
