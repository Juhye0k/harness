"""Usage: uv run python -m app.cli.extract_clip --url URL --start 12.5"""

import argparse
import json

from app.services.video import execute


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(
            1,
            json.dumps(
                {
                    "status": "failed",
                    "stage": "input",
                    "error": {
                        "code": "INVALID_INPUT",
                        "message": "--url 링크와 --start 초 단위 숫자를 입력하세요.",
                    },
                },
                ensure_ascii=True,
            )
            + "\n",
        )


def main() -> int:
    parser = Parser(description="영상 링크에서 10초 MP4를 추출합니다.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--start", required=True, type=float)
    arguments = parser.parse_args()
    try:
        result = execute(arguments.url, arguments.start)
    except OSError:
        result = {
            "status": "failed",
            "stage": "storage",
            "error": {
                "code": "IO_FAILED",
                "message": "결과 폴더나 JSON 파일을 저장할 수 없습니다.",
            },
        }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
