"""Real portrait rendering, caption appearance, trim position, and audio-track checks."""

import json
import subprocess
from pathlib import Path

import pytest

from app.adapters.media import probe
from app.adapters.portrait import render_portrait
from app.adapters.process import executable, run
from app.domain.video import VideoError
from app.services.portrait_sample import execute
from app.services.video import checksum


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
