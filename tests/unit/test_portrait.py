"""Portrait timing and safe fixture text; no media tools or network in unit tests."""

from copy import deepcopy

import pytest

from app.adapters import portrait
from app.domain.portrait import ass_document, clip_captions
from app.domain.video import VideoError
from app.services import portrait_sample


def test_source_times_become_clip_times_without_mutating_original():
    source = [{"start_ms": 62500, "end_ms": 63700, "lines": ["한국어 자막", "확인!"]}]
    before = deepcopy(source)
    cues = clip_captions(source, 60000, 10000)
    assert cues == [{"start_ms": 2500, "end_ms": 3700, "lines": ["한국어 자막", "확인!"]}]
    assert source == before
    cues[0]["lines"].append("별도 편집")
    assert source == before
    document = ass_document(cues[:1], "Malgun Gothic")
    assert "0:00:02.50,0:00:03.70" in document
    assert r"한국어 자막\N확인!" in document


@pytest.mark.parametrize("start,duration", [(-1, 1000), (True, 1000), (0, 0), (0, 60001)])
def test_invalid_clip_range(start, duration):
    with pytest.raises(VideoError, match="밀리초"):
        clip_captions([], start, duration)


@pytest.mark.parametrize(
    "cues",
    [
        [],
        [{"start_ms": 500, "end_ms": 1500, "lines": ["앞 경계 잘림"]}],
        [{"start_ms": 1500, "end_ms": 2500, "lines": ["뒤 경계 잘림"]}],
        [{"start_ms": 1500, "end_ms": 1500, "lines": ["길이 없음"]}],
        [{"start_ms": True, "end_ms": 1500, "lines": ["잘못된 시각"]}],
        [
            {"start_ms": 1000, "end_ms": 1800, "lines": ["첫 자막"]},
            {"start_ms": 1700, "end_ms": 2000, "lines": ["겹침"]},
        ],
    ],
)
def test_invalid_or_cut_cues_are_rejected_not_trimmed(cues):
    with pytest.raises(VideoError) as failure:
        clip_captions(cues, 1000, 1000)
    assert failure.value.code == "SUBTITLE_INVALID"


@pytest.mark.parametrize(
    "lines", [[r"{\pos(0,0)}숨김"], [r"명령\N주입"], ["줄\n바꿈"], ["a" * 15], [" "]]
)
def test_fixture_rejects_ass_controls_and_unsupported_text(lines):
    with pytest.raises(VideoError) as failure:
        clip_captions([{"start_ms": 0, "end_ms": 1000, "lines": lines}], 0, 1000)
    assert failure.value.code == "SUBTITLE_INVALID"


def test_existing_result_and_source_are_not_overwritten(tmp_path):
    path = tmp_path / "source.mp4"
    path.write_bytes(b"original")
    with pytest.raises(VideoError) as failure:
        portrait.render_portrait(path, path, [], 0, 1000)
    assert failure.value.code == "OUTPUT_CONFLICT"
    assert path.read_bytes() == b"original"
    target = tmp_path / "existing.mp4"
    target.write_bytes(b"previous result")
    with pytest.raises(VideoError):
        portrait.render_portrait(path, target, [], 0, 1000)
    assert target.read_bytes() == b"previous result"
    with pytest.raises(VideoError):
        portrait_sample.execute(tmp_path)
    assert path.read_bytes() == b"original"


def test_missing_font_is_explicit(monkeypatch):
    monkeypatch.setattr(portrait.Path, "is_file", lambda _: False)
    with pytest.raises(VideoError) as failure:
        portrait.korean_font()
    assert failure.value.code == "FONT_MISSING"


def test_render_failure_does_not_publish_or_leave_workspace(tmp_path, monkeypatch):
    from app.domain.video import MediaInfo

    source, font = tmp_path / "source.mp4", tmp_path / "font.ttf"
    source.write_bytes(b"original")
    font.write_bytes(b"font")
    monkeypatch.setattr(portrait, "probe", lambda *a, **kw: MediaInfo(12, True, 12))
    monkeypatch.setattr(portrait, "korean_font", lambda: (font, "Malgun Gothic"))
    monkeypatch.setattr(portrait, "executable", lambda name: name)
    monkeypatch.setattr(portrait, "container", lambda *a: "mov")

    def fail(args, timeout, **kwargs):
        # Filters only name trusted relative files; user directory text stays out of the graph.
        assert "ass=filename=captions.ass:fontsdir=fonts" in args[args.index("-vf") + 1]
        assert kwargs["cwd"].parent == tmp_path
        raise VideoError("TIMEOUT", "timeout")

    monkeypatch.setattr(portrait, "run", fail)
    with pytest.raises(VideoError) as failure:
        portrait.render_portrait(
            source,
            tmp_path / "clip.mp4",
            [{"start_ms": 1000, "end_ms": 2000, "lines": ["확인"]}],
            0,
            10000,
        )
    assert failure.value.code == "TIMEOUT"
    assert source.read_bytes() == b"original"
    assert not (tmp_path / "clip.mp4").exists()
    assert not list(tmp_path.glob(".portrait-*"))


def test_sample_failure_removes_outputs_but_preserves_source(tmp_path, monkeypatch):
    monkeypatch.setattr(portrait_sample, "executable", lambda name: name)

    def fake_run(args, timeout):
        if "-version" in args:
            return "test-version"
        (tmp_path / "sample" / "source.mp4").write_bytes(b"original")
        return ""

    def fail(source, target, *args):
        target.write_bytes(b"partial")
        raise VideoError("OUTPUT_INVALID", "fixture failure")

    monkeypatch.setattr(portrait_sample, "run", fake_run)
    monkeypatch.setattr(portrait_sample, "render_portrait", fail)
    result = portrait_sample.execute(tmp_path / "sample")
    assert result["status"] == "failed"
    assert result["error"]["code"] == "OUTPUT_INVALID"
    assert not (tmp_path / "sample" / "clip.mp4").exists()
    assert (tmp_path / "sample" / "source.mp4").read_bytes() == b"original"


@pytest.mark.parametrize("failure_stage", ["dimensions", "decode", "source_changed"])
def test_failed_output_checks_never_publish(tmp_path, monkeypatch, failure_stage):
    from app.domain.video import MediaInfo

    source, font = tmp_path / "source.mp4", tmp_path / "font.ttf"
    source.write_bytes(b"original")
    font.write_bytes(b"font")
    monkeypatch.setattr(
        portrait,
        "probe",
        lambda path, **kwargs: MediaInfo(3 if kwargs.get("output") else 4, True),
    )
    monkeypatch.setattr(portrait, "korean_font", lambda: (font, "Malgun Gothic"))
    monkeypatch.setattr(portrait, "executable", lambda name: name)
    monkeypatch.setattr(portrait, "container", lambda *a: "mov")

    def fake_run(args, timeout, **kwargs):
        if args[0] == "ffprobe":
            width = 640 if failure_stage == "dimensions" else 720
            return (
                '{"streams":[{"width":'
                + str(width)
                + ',"height":1280,"sample_aspect_ratio":"1:1"}]}'
            )
        if "-vf" in args:
            (kwargs["cwd"] / "clip.mp4").write_bytes(b"staged")
            if failure_stage == "source_changed":
                source.write_bytes(b"changed by another process")
        elif failure_stage == "decode":
            raise VideoError("TOOL_FAILED", "decode failure")
        return ""

    monkeypatch.setattr(portrait, "run", fake_run)
    with pytest.raises(VideoError):
        portrait.render_portrait(
            source,
            tmp_path / "final.mp4",
            [{"start_ms": 1500, "end_ms": 2500, "lines": ["확인"]}],
            1000,
            3000,
        )
    assert not (tmp_path / "final.mp4").exists()
    assert not list(tmp_path.glob(".portrait-*"))
