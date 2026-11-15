import pytest

from app.adapters import media
from app.domain.video import VideoError


def test_missing_file(tmp_path):
    with pytest.raises(VideoError) as failure:
        media.probe(tmp_path / "missing.mp4")
    assert failure.value.code == "INVALID_MEDIA"


def test_existing_output_untouched(tmp_path):
    path = tmp_path / "original.mp4"
    path.write_bytes(b"original")
    with pytest.raises(VideoError):
        media.extract(path, path, 0)
    assert path.read_bytes() == b"original"
