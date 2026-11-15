"""Bounded subprocess execution; never run user input through a shell."""

import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import psutil

from app.domain.video import VideoError


def executable(name: str) -> str:
    path = shutil.which(name)
    if not path and os.name == "nt":
        tool_root = Path(__file__).resolve().parents[2] / ".tmp" / "tools"
        candidates = (
            list(tool_root.glob(f"ffmpeg/*/bin/{name}.exe"))
            if name in {"ffmpeg", "ffprobe"}
            else [tool_root / "deno" / "deno.exe"]
            if name == "deno"
            else []
        )
        if len(candidates) == 1 and candidates[0].is_file():
            path = str(candidates[0])
    if not path:
        raise VideoError("TOOL_MISSING", f"{name} 실행 파일이 없습니다. 설치 후 PATH를 확인하세요.")
    return path


def terminate_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        try:
            parent = psutil.Process(process.pid)
            parent.suspend()
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.suspend()
                except psutil.NoSuchProcess:
                    pass
            for child in [*reversed(children), parent]:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs([*children, parent], timeout=5)
            if alive:
                raise VideoError(
                    "TERMINATION_FAILED", "일부 하위 프로세스 종료를 확인하지 못했습니다."
                )
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            process.kill()
            raise VideoError("TERMINATION_FAILED", "하위 프로세스를 종료할 수 없습니다.") from exc
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise VideoError("TERMINATION_FAILED", "프로세스 종료를 확인하지 못했습니다.") from exc


def run(
    args: list[str],
    timeout: float,
    *,
    watch_dir: Path | None = None,
    max_bytes: int | None = None,
    input_text: str | None = None,
) -> str:
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {
            "start_new_session": True,
        }
    )
    # stderr is deliberately not retained: download tools may print signed URLs.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as input_file:
        if input_text is not None:
            input_file.write(input_text.encode("utf-8"))
            input_file.seek(0)
        try:
            process = subprocess.Popen(
                args,
                stdin=input_file,
                stdout=output,
                stderr=subprocess.DEVNULL,
                shell=False,
                **options,
            )
        except FileNotFoundError as exc:
            raise VideoError("TOOL_MISSING", "실행 도구를 찾을 수 없습니다.") from exc
        except OSError as exc:
            raise VideoError("TOOL_FAILED", "외부 도구를 실행할 수 없습니다.") from exc
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise VideoError("TIMEOUT", "처리 제한 시간을 초과했습니다.")
                if watch_dir is not None and max_bytes is not None:
                    total = 0
                    for path in watch_dir.rglob("*"):
                        try:
                            if path.is_file():
                                total += path.stat().st_size
                        except FileNotFoundError:
                            continue
                    if total > max_bytes:
                        raise VideoError(
                            "LIMIT_EXCEEDED", "다운로드 작업 공간이 500MiB를 넘었습니다."
                        )
                time.sleep(0.05)
        except BaseException:
            terminate_tree(process)
            raise
        output.seek(0)
        text = output.read(1024 * 1024).decode("utf-8", errors="replace")
        if process.returncode:
            raise VideoError("TOOL_FAILED", "외부 도구가 비정상 종료했습니다.")
        return text
