import json
from pathlib import Path

from app.domain.video import VideoError
from app.services import video


def test_failed_report_is_sanitized(tmp_path):
    result = video.execute("https://user:secret@example.com/a?token=secret", -1, tmp_path)
    report = Path(result["result_path"]).read_text(encoding="utf-8")
    assert "secret" not in report
    assert json.loads(report)["error"]["code"] == "INVALID_INPUT"


def test_failure_cleans_output_but_preserves_source(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "executable", lambda name: name)
    monkeypatch.setattr(video, "run", lambda *a, **kw: "version")

    def download(url, directory):
        path = directory / "source.mp4"
        path.write_bytes(b"original")
        return path

    def extract(source, target, start):
        target.write_bytes(b"partial")
        raise VideoError("TIMEOUT", "timeout")

    monkeypatch.setattr(video, "download", download)
    monkeypatch.setattr(video, "extract", extract)
    result = video.execute("https://example.com/video", 0, tmp_path)
    assert result["error"]["code"] == "TIMEOUT"
    directory = Path(result["result_path"]).parent
    assert (directory / "source/source.mp4").read_bytes() == b"original"
    assert not list((directory / "work").iterdir())
    assert not list((directory / "output").iterdir())
