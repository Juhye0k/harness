import sys
import time

import pytest

from app.adapters.process import run
from app.domain.video import VideoError


def test_process_failure():
    with pytest.raises(VideoError) as failure:
        run([sys.executable, "-c", "raise SystemExit(3)"], 5)
    assert failure.value.code == "TOOL_FAILED"


def test_process_timeout():
    with pytest.raises(VideoError) as failure:
        run([sys.executable, "-c", "import time; time.sleep(10)"], 0.1)
    assert failure.value.code == "TIMEOUT"


def test_timeout_kills_descendants(tmp_path):
    marker = tmp_path / "child-finished"
    child = f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).touch()"
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(20)"
    )
    with pytest.raises(VideoError) as failure:
        run([sys.executable, "-c", parent], 0.5)
    assert failure.value.code == "TIMEOUT"
    time.sleep(2)
    assert not marker.exists()


def test_download_workspace_limit(tmp_path):
    program = (
        "from pathlib import Path; import time; "
        f"Path({str(tmp_path / 'partial')!r}).write_bytes(b'x'*100); time.sleep(10)"
    )
    with pytest.raises(VideoError) as failure:
        run([sys.executable, "-c", program], 5, watch_dir=tmp_path, max_bytes=50)
    assert failure.value.code == "LIMIT_EXCEEDED"


def test_missing_tool():
    with pytest.raises(VideoError) as failure:
        run(["nonexistent-shortform-tool-123"], 1)
    assert failure.value.code == "TOOL_MISSING"
