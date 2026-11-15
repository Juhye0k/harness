"""Operator confirms stopped execution; this command is NOT a failure detector."""

import argparse
import json
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.adapters.job_repository import JobRepository


def main():
    parser = argparse.ArgumentParser(description="실행 중단을 확인한 작업만 실패 확정합니다.")
    parser.add_argument("job_id", type=UUID)
    parser.add_argument("--confirmed-stopped", action="store_true", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if not args.reason.strip() or len(args.reason) > 500:
        parser.error("사유는 1~500자로 입력하세요. 비밀값을 포함하지 마세요.")
    try:
        changed = JobRepository().mark_interrupted(args.job_id, args.reason.strip())
    except SQLAlchemyError:
        print(json.dumps({"error": "DATABASE_UNAVAILABLE"}))
        return 1
    print(json.dumps({"job_id": str(args.job_id), "changed": changed}))
    return 0 if changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
