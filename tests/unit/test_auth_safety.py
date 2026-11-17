import pytest

from app.api.auth import csrf, digest
from app.cli.cleanup_data import remove_tree


def test_deletion_path_boundaries(tmp_path):
    root = tmp_path / "managed"
    root.mkdir()
    other = tmp_path / "outside"
    other.mkdir()
    (other / "private").write_text("preserve")
    for path in ("../outside", ".", str(other)):
        with pytest.raises(ValueError):
            remove_tree(root, path)
    assert (other / "private").read_text() == "preserve"


def test_session_hashes_and_csrf_do_not_expose_token():
    assert len(digest("token")) == 64
    assert csrf("a") != csrf("b")
    assert csrf("token") != digest("token")
