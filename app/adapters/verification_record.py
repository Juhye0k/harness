"""Read an operator-provided code verification record, bound to deployed app bytes."""

import hashlib
import json
import os
from pathlib import Path


def source_hash():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def code_status():
    from app.config import get_settings

    path = os.getenv("VERIFICATION_RECORD") or str(
        get_settings().video_data_dir / "verification-code.json"
    )
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data["app_sha256"] != source_hash():
            return {"status": "stale", "recorded_at": data.get("recorded_at")}
        checks = data["checks"]
        passed = all(checks.get(key) is True for key in ("basic", "integration"))
        return {
            "status": "passed" if passed else "incomplete",
            "checks": checks,
            "recorded_at": data.get("recorded_at"),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unknown"}
