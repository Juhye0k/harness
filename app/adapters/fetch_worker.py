"""Isolated download process: the parent enforces wall time and disk limits."""

import http.client
import json
import sys
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.adapters.download import download_direct, validate_url
from app.adapters.process import executable
from app.domain.video import MAX_BYTES, MAX_SECONDS, VideoError


class QuietLogger:
    def debug(self, message):
        pass

    info = debug
    warning = debug
    error = debug


def download_youtube(url: str, directory: Path) -> Path:
    totals: dict[str, int] = {}

    def progress(event):
        filename = event.get("filename", "unknown")
        totals[filename] = event.get("downloaded_bytes", totals.get(filename, 0))
        if sum(totals.values()) > MAX_BYTES:
            raise VideoError("LIMIT_EXCEEDED", "다운로드가 500MiB를 넘었습니다.")

    def reject(info, *, incomplete=False):
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise VideoError("INVALID_INPUT", "라이브 방송은 지원하지 않습니다.")
        duration = info.get("duration")
        if duration is not None and duration > MAX_SECONDS:
            raise VideoError("LIMIT_EXCEEDED", "원본 영상은 20분 이하여야 합니다.")
        known_size = info.get("filesize") or sum(
            item.get("filesize") or 0 for item in (info.get("requested_formats") or [])
        )
        if known_size > MAX_BYTES:
            raise VideoError("LIMIT_EXCEEDED", "다운로드가 500MiB를 넘었습니다.")
        return None

    options = {
        "format": "bv*[height<=720]+ba/b[height<=720]",
        "outtmpl": str(directory / "source.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "overwrites": False,
        "continuedl": False,
        "retries": 0,
        "fragment_retries": 0,
        "extractor_retries": 0,
        "file_access_retries": 0,
        "socket_timeout": 15,
        "progress_hooks": [progress],
        "match_filter": reject,
        "logger": QuietLogger(),
        "quiet": True,
        "noprogress": True,
        "js_runtimes": {"deno": {"path": executable("deno")}},
        "ffmpeg_location": str(Path(executable("ffmpeg")).parent),
        "remote_components": [],
        "proxy": "",
        "restrictfilenames": True,
    }
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=True)
        if not info or info.get("_type") in {"playlist", "multi_video"}:
            raise VideoError("INVALID_INPUT", "단일 영상만 지원합니다.")
    files = [p for p in directory.glob("source.*") if p.suffix in {".mp4", ".webm", ".mkv"}]
    if len(files) != 1:
        raise VideoError("DOWNLOAD_FAILED", "완료된 영상 파일을 확인할 수 없습니다.")
    return files[0]


def main() -> None:
    # URL arrives on stdin, rather than in a process command line or log.
    request = json.loads(sys.stdin.read())
    directory = Path(request["directory"])
    try:
        kind, url = validate_url(request["url"])
        if kind == "youtube":
            path = download_youtube(url, directory)
        else:
            path = directory / "source.mp4"
            download_direct(url, path)
        if path.stat().st_size > MAX_BYTES:
            raise VideoError("LIMIT_EXCEEDED", "다운로드가 500MiB를 넘었습니다.")
        result = {"path": str(path)}
    except VideoError as exc:
        result = {"error": exc.code, "message": str(exc)}
    except TimeoutError:
        result = {"error": "TIMEOUT", "message": "다운로드 연결 시간이 초과되었습니다."}
    except DownloadError as exc:
        timed_out = "timed out" in str(exc).lower() or "timeout" in str(exc).lower()
        result = {
            "error": "TIMEOUT" if timed_out else "DOWNLOAD_FAILED",
            "message": "YouTube 응답 시간이 초과되었습니다."
            if timed_out
            else "YouTube 영상을 내려받지 못했습니다. 공개 단일 영상인지 확인하세요.",
        }
    except (OSError, ValueError, http.client.HTTPException):
        result = {
            "error": "DOWNLOAD_FAILED",
            "message": "영상을 내려받지 못했습니다. 링크와 접근 가능 여부를 확인하세요.",
        }
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
