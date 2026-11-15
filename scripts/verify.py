"""Single local/CI verification entry point; commands never invoke a shell."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    [sys.executable, "-m", "ruff", "check", "."],
    [sys.executable, "-m", "ruff", "format", "--check", "."],
    [sys.executable, "-m", "pytest", "-m", "not integration", "-q"],
    [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
]


def main() -> int:
    for command in COMMANDS:
        print("\n> " + " ".join(command[1:]), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
