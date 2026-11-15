"""Real FFmpeg checks: missing tools fail, never silently skip."""

import subprocess

import pytest

from app.adapters.media import extract, probe
from app.adapters.process import executable, run
from app.domain.video import VideoError
from app.services import video
from app.services.video import checksum


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    directory = tmp_path_factory.mktemp("media")
    path = directory / "sample.mp4"
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
            "color=c=red:s=160x90:r=30:d=10",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x90:r=30:d=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=20",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        30,
    )
    return path


@pytest.mark.parametrize("start", [0, 7.5, 10])
def test_real_extract(sample, tmp_path, start):
    before = checksum(sample)
    output = tmp_path / "clip.mp4"
    info, checks = extract(sample, output, start)
    assert abs(info.duration - 10) <= 0.1
    assert info.has_audio
    assert all(checks.values())
    assert checksum(sample) == before
    if start == 7.5:
        # The source switches red -> blue at 10s, so the clip switches at 2.5s.
        for second, channel in [(2, 0), (3, 2)]:
            frame = subprocess.check_output(
                [
                    executable("ffmpeg"),
                    "-v",
                    "error",
                    "-ss",
                    str(second),
                    "-i",
                    str(output),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=1:1",
                    "-pix_fmt",
                    "rgb24",
                    "-f",
                    "rawvideo",
                    "-",
                ],
                timeout=10,
            )
            assert frame[channel] > 200
            assert frame[2 if channel == 0 else 0] < 30


def test_silent_video(sample, tmp_path):
    silent = tmp_path / "silent.mp4"
    run(
        [
            executable("ffmpeg"),
            "-v",
            "error",
            "-n",
            "-i",
            str(sample),
            "-c:v",
            "copy",
            "-an",
            str(silent),
        ],
        30,
    )
    info, checks = extract(silent, tmp_path / "clip.mp4", 0)
    assert not info.has_audio
    assert all(checks.values())


def test_corrupt_file(tmp_path):
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"not a movie")
    with pytest.raises(VideoError) as failure:
        probe(path)
    assert failure.value.code == "INVALID_MEDIA"


def test_audio_only(tmp_path):
    path = tmp_path / "audio.m4a"
    run(
        [
            executable("ffmpeg"),
            "-v",
            "error",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=12",
            "-c:a",
            "aac",
            str(path),
        ],
        30,
    )
    with pytest.raises(VideoError) as failure:
        probe(path)
    assert failure.value.code == "INVALID_MEDIA"


def test_use_case_publishes_validated_result(sample, tmp_path, monkeypatch):
    import json
    import shutil
    from pathlib import Path

    def download(url, directory):
        destination = directory / "source.mp4"
        shutil.copyfile(sample, destination)
        return destination

    monkeypatch.setattr(video, "download", download)
    result = video.execute("https://example.com/sample.mp4", 7.5, tmp_path)
    assert result["status"] == "succeeded"
    assert all(result["checks"].values())
    assert Path(result["output_path"]).is_file()
    assert json.loads(Path(result["result_path"]).read_text(encoding="utf-8")) == result
    assert not list((Path(result["result_path"]).parent / "work").iterdir())
