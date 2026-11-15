import io
import socket

import pytest

from app.adapters import download as http
from app.domain.video import VideoError


@pytest.mark.parametrize(
    "url",
    [
        "",
        "file:///test.mp4",
        "http://u:p@host/a",
        "http://host:123/a",
        "https://youtube.com/playlist?list=abc",
        "https://youtube.com/watch?v=abcdefghijk&list=abc",
    ],
)
def test_bad_url(url):
    with pytest.raises(VideoError):
        http.validate_url(url)


def test_youtube_canonical_url():
    assert http.validate_url("https://youtu.be/abcdefghijk?t=12") == (
        "youtube",
        "https://www.youtube.com/watch?v=abcdefghijk",
    )


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_private_address(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(0, 0, 0, "", (ip, 80))])
    with pytest.raises(VideoError, match="주소"):
        http.public_address("host", 80)


def test_connection_pins_validated_address(monkeypatch):
    monkeypatch.setattr(http, "public_address", lambda *args: "93.184.216.34")
    calls = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: calls.append(a))
    conn = http.open_connection("https://example.com/video.mp4")
    conn._create_connection(("example.com", 443))
    assert calls == [(("93.184.216.34", 443),)]
    assert conn.host == "example.com"


class Response(io.BytesIO):
    def __init__(self, body=b"video", status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def getheader(self, name):
        return self.headers.get(name)


class Connection:
    def __init__(self, response):
        self.response = response

    def request(self, *args, **kwargs):
        pass

    def getresponse(self):
        return self.response

    def close(self):
        pass


def test_direct_download(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "open_connection", lambda url: Connection(Response()))
    target = tmp_path / "source.mp4"
    http.download_direct("https://example.com/video", target)
    assert target.read_bytes() == b"video"


@pytest.mark.parametrize("headers,body", [({"Content-Length": "6"}, b"123456"), ({}, b"123456")])
def test_size_limit(monkeypatch, tmp_path, headers, body):
    monkeypatch.setattr(http, "MAX_BYTES", 5)
    monkeypatch.setattr(
        http, "open_connection", lambda url: Connection(Response(body, headers=headers))
    )
    with pytest.raises(VideoError) as failure:
        http.download_direct("https://example.com/video", tmp_path / "source.mp4")
    assert failure.value.code == "LIMIT_EXCEEDED"


def test_redirect_revalidates_destination(monkeypatch, tmp_path):
    original = http.open_connection
    calls = []

    def connect(url):
        calls.append(url)
        if len(calls) == 1:
            return Connection(Response(status=302, headers={"Location": "http://127.0.0.1/a"}))
        return original(url)

    monkeypatch.setattr(http, "open_connection", connect)
    with pytest.raises(VideoError, match="주소"):
        http.download_direct("https://example.com/video", tmp_path / "source.mp4")
    assert len(calls) == 2


@pytest.mark.parametrize("status", [403, 404, 500])
def test_http_failure(monkeypatch, tmp_path, status):
    monkeypatch.setattr(http, "open_connection", lambda url: Connection(Response(status=status)))
    with pytest.raises(VideoError) as failure:
        http.download_direct("https://example.com/video", tmp_path / "source.mp4")
    assert failure.value.code == "DOWNLOAD_FAILED"
