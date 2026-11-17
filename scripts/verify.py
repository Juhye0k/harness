"""Single local/CI verification entry point; commands never invoke a shell."""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    [sys.executable, "-m", "ruff", "check", "."],
    [sys.executable, "-m", "ruff", "format", "--check", "."],
    [sys.executable, "-m", "pytest", "-m", "not integration", "-q"],
    [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / ".artifacts/verification/latest.json")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from app.adapters.verification_record import source_hash

    started_hash = source_hash()
    record = {
        "app_sha256": started_hash,
        "recorded_at": datetime.now(UTC).isoformat(),
        "checks": {"basic": False, "integration": None},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(record, indent=2), encoding="utf-8")
    for command in COMMANDS:
        print("\n> " + " ".join(command[1:]), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    if source_hash() != started_hash:
        return 2
    record["checks"]["basic"] = True
    args.report.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
