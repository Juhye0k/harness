"""After stopping an interrupted SNS worker, preserve uncertainty; never retry."""

import argparse
from uuid import UUID

from app.adapters.sns_repository import SnsRepository


def main():
    parser = argparse.ArgumentParser(description="중단한 running 업로드를 unknown으로 기록")
    parser.add_argument("upload_id", type=UUID)
    parser.add_argument("--worker-stopped", action="store_true", required=True)
    args = parser.parse_args()
    changed = SnsRepository().mark_unknown(args.upload_id)
    print("unknown 기록 완료" if changed else "변경 없음: running 상태가 아닙니다.")
    return 0 if changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
