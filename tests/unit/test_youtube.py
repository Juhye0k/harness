"""Exercise the YouTube adapter contract without calling YouTube in CI."""

import pytest

from app.adapters import fetch_worker
from app.domain.video import VideoError


def install_fake(monkeypatch, tmp_path, info, *, progress=None):
    captured = {}
    monkeypatch.setattr(fetch_worker, "executable", lambda name: f"/tools/{name}")

    class Downloader:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            captured["match_filter"](info)
            if progress:
                for event in progress:
                    captured["progress_hooks"][0](event)
            (tmp_path / "source.mp4").write_bytes(b"sample")
            return info

    monkeypatch.setattr(fetch_worker, "YoutubeDL", Downloader)
    return captured


def test_youtube_configuration(monkeypatch, tmp_path):
    options = install_fake(monkeypatch, tmp_path, {"id": "abcdefghijk", "duration": 20})
    path = fetch_worker.download_youtube("https://www.youtube.com/watch?v=abcdefghijk", tmp_path)
    assert path.name == "source.mp4"
    assert options["noplaylist"] is True
    assert options["overwrites"] is False
    assert options["remote_components"] == []
    assert options["js_runtimes"] == {"deno": {"path": "/tools/deno"}}


@pytest.mark.parametrize(
    "info,code",
    [
        ({"is_live": True}, "INVALID_INPUT"),
        ({"live_status": "is_upcoming"}, "INVALID_INPUT"),
        ({"duration": 1201}, "LIMIT_EXCEEDED"),
        ({"_type": "playlist"}, "INVALID_INPUT"),
    ],
)
def test_youtube_rejections(monkeypatch, tmp_path, info, code):
    install_fake(monkeypatch, tmp_path, info)
    with pytest.raises(VideoError) as failure:
        fetch_worker.download_youtube("https://www.youtube.com/watch?v=abcdefghijk", tmp_path)
    assert failure.value.code == code


def test_combined_download_size(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_worker, "MAX_BYTES", 10)
    install_fake(
        monkeypatch,
        tmp_path,
        {"duration": 20},
        progress=[
            {"filename": "video", "downloaded_bytes": 6},
            {"filename": "audio", "downloaded_bytes": 6},
        ],
    )
    with pytest.raises(VideoError) as failure:
        fetch_worker.download_youtube("https://www.youtube.com/watch?v=abcdefghijk", tmp_path)
    assert failure.value.code == "LIMIT_EXCEEDED"
