"""URL routing and pinned, public-address HTTP downloads."""

import http.client
import ipaddress
import re
import socket
import ssl
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from app.domain.video import MAX_BYTES, VideoError

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def validate_url(url: str) -> tuple[str, str]:
    try:
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or any(ord(c) <= 32 for c in url)
        ):
            raise ValueError()
        if parts.port not in {None, 80, 443}:
            raise ValueError()
        if parts.hostname.lower() in YOUTUBE_HOSTS:
            query = parse_qs(parts.query)
            if "list" in query:
                raise ValueError()
            if parts.hostname.lower() == "youtu.be":
                video_id = parts.path.lstrip("/")
            elif parts.path == "/watch":
                video_id = query.get("v", [""])[0]
            elif parts.path.startswith(("/shorts/", "/embed/")):
                video_id = parts.path.split("/")[-1]
            else:
                raise ValueError()
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                raise ValueError()
            return "youtube", "https://www.youtube.com/watch?" + urlencode({"v": video_id})
        return "direct", urlunsplit(parts._replace(fragment=""))
    except ValueError as exc:
        raise VideoError("INVALID_INPUT", "지원하는 단일 영상 HTTP(S) 링크를 입력하세요.") from exc


def public_address(host: str, port: int) -> str:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise VideoError("DOWNLOAD_FAILED", "영상 서버 주소를 확인할 수 없습니다.") from exc
    ips = [entry[4][0] for entry in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise VideoError("INVALID_INPUT", "로컬·사설·예약 주소로 접속할 수 없습니다.")
    return ips[0]


def open_connection(url: str):
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    address = public_address(parts.hostname, port)
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(
            parts.hostname,
            port,
            timeout=15,
            context=ssl.create_default_context(),
        )
    else:
        connection = http.client.HTTPConnection(parts.hostname, port, timeout=15)
    # Pin the validated IP while retaining the original HTTP Host and TLS SNI.
    connection._create_connection = lambda *args, **kwargs: socket.create_connection(
        (address, port),
        timeout=15,
    )
    return connection


def download_direct(url: str, target: Path) -> None:
    for _ in range(6):
        kind, url = validate_url(url)
        if kind != "direct":
            raise VideoError("INVALID_INPUT", "직접 링크가 영상 파일 대신 YouTube로 이동했습니다.")
        connection = open_connection(url)
        try:
            parts = urlsplit(url)
            path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
            connection.request("GET", path, headers={"Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise VideoError("DOWNLOAD_FAILED", "리디렉션 목적지가 없습니다.")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise VideoError("DOWNLOAD_FAILED", f"영상 서버 HTTP 오류: {response.status}")
            length = response.getheader("Content-Length")
            if length and (not length.isdigit() or int(length) > MAX_BYTES):
                raise VideoError("LIMIT_EXCEEDED", "다운로드 크기가 허용 범위를 넘습니다.")
            size = 0
            with target.open("xb") as output:
                while chunk := response.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise VideoError("LIMIT_EXCEEDED", "다운로드가 500MiB를 넘었습니다.")
                    output.write(chunk)
            if length and size != int(length):
                raise VideoError("DOWNLOAD_FAILED", "영상 다운로드가 완료되지 않았습니다.")
            return
        finally:
            connection.close()
    raise VideoError("DOWNLOAD_FAILED", "리디렉션 횟수 제한을 초과했습니다.")
