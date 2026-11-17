from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.video import MediaInfo
from app.services.uploads import upload_directory, validate_upload
from app.services.video import checksum


@pytest.mark.parametrize("failure", ["length", "changed", "long"])
def test_rejected_source_never_becomes_ready(tmp_path, monkeypatch, failure):
    from app.config import get_settings

    monkeypatch.setattr("app.services.access.get_engine", lambda: None)
    monkeypatch.setattr(
        "app.config.get_settings", lambda: get_settings().model_copy(update={"enable_auth": False})
    )
    uid = uuid4()
    inbox = tmp_path / "incoming"
    directory = upload_directory(inbox, uid)
    directory.mkdir(parents=True)
    source = directory / "received.bin"
    source.write_bytes(b"private-source")
    receipt = SimpleNamespace(
        expected_bytes=source.stat().st_size + (1 if failure == "length" else 0),
        sha256="wrong" if failure == "changed" else checksum(source),
    )
    monkeypatch.setattr("app.services.uploads.probe", lambda p: MediaInfo(1201, True))

    class Repo:
        def claim(self, *args):
            return receipt

        def finish(self, *args, **kwargs):
            self.result = kwargs
            return True

    repo = Repo()
    validate_upload(
        uid, repo, SimpleNamespace(upload_data_dir=inbox, video_data_dir=tmp_path / "originals")
    )
    assert repo.result["error"] in {"UPLOAD_INCOMPLETE", "SOURCE_CHANGED", "LIMIT_EXCEEDED"}
    assert source.read_bytes() == b"private-source"
    assert not (tmp_path / "originals" / "assets" / str(uid) / "source.bin").exists()


def test_filename_never_becomes_storage_path(tmp_path):
    uid = uuid4()
    assert upload_directory(tmp_path, uid) == tmp_path / str(uid)
    with pytest.raises(ValueError):
        upload_directory(tmp_path, "../../private")
