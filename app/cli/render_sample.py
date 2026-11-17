"""Usage: uv run python -m app.cli.render_sample [--output-dir NEW_DIRECTORY]."""

import argparse
import json
from pathlib import Path

from app.domain.video import VideoError
from app.services.portrait_sample import execute


def main() -> int:
    parser = argparse.ArgumentParser(
        description="합성 영상으로 한국어 자막 포함 세로 MP4를 확인합니다."
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        result = execute(args.output_dir)
    except VideoError as exc:
        result = {"status": "failed", "error": {"code": exc.code, "message": str(exc)}}
    except OSError:
        result = {"status": "failed", "error": {"code": "IO_FAILED", "message": "저장 실패"}}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
