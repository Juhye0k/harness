"""Offline human evaluation and read-only result capture; never submits paid jobs."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Interval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must exceed start_ms")
        return self


class Rating(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    candidate_id: str
    usable: bool | None = None
    boundaries: int | None = Field(default=None, ge=0, le=4)
    independence: int | None = Field(default=None, ge=0, le=4)
    notes: str = ""
    selected: bool | None = None
    uncertain: bool = False
    edited_range: Interval | None = None
    reasons: list[
        Literal["preference", "context", "boundary", "transcription", "duplicate", "title", "other"]
    ] = Field(default_factory=list)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    analysis_id: str
    split: Literal["development", "holdout"]
    reviewer: str = ""
    references: list[Interval] = Field(default_factory=list)
    ratings: list[Rating]
    transcription_notes: str = ""
    diversity_notes: str = ""
    snapshot_sha256: str | None = None
    policy_version: str = "human-v1"


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def save_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def iou(left, right):
    intersection = max(0, min(left.end_ms, right.end_ms) - max(left.start_ms, right.start_ms))
    union = left.end_ms - left.start_ms + right.end_ms - right.start_ms - intersection
    return intersection / union


def summarize(snapshot: dict, review: Review):
    if snapshot["status"] != "succeeded" or snapshot["analysis_id"] != review.analysis_id:
        raise ValueError("완료된 동일 분석의 결과와 평가표가 필요합니다.")
    candidates = snapshot["candidates"]
    frozen = snapshot.get("evaluation_input")
    if frozen:
        if review.snapshot_sha256 != fingerprint(snapshot):
            raise ValueError("평가표와 고정 결과의 해시가 다릅니다.")
        for rating in review.ratings:
            if (rating.usable is False or rating.edited_range) and not rating.reasons:
                raise ValueError("사용 불가 또는 구간 수정에는 이유가 필요합니다.")
            if rating.uncertain and rating.usable is not None:
                raise ValueError("판단 보류와 사용 가능 판정을 동시에 지정할 수 없습니다.")
            if rating.edited_range and rating.edited_range.end_ms > frozen["duration_ms"]:
                raise ValueError("수정 구간이 원본 범위를 초과했습니다.")
    ids = [c["id"] for c in candidates]
    rating_ids = [r.candidate_id for r in review.ratings]
    if (
        len(set(ids)) != len(ids)
        or len(set(rating_ids)) != len(rating_ids)
        or set(ids) != set(rating_ids)
    ):
        raise ValueError("후보마다 정확히 하나의 평가 행이 필요합니다.")
    rated = [r for r in review.ratings if r.usable is not None]
    complete = (
        bool(candidates)
        and bool(review.reviewer.strip())
        and all(
            r.usable is not None and r.boundaries is not None and r.independence is not None
            for r in review.ratings
        )
    )
    intervals = [Interval(start_ms=c["start_ms"], end_ms=c["end_ms"]) for c in candidates]
    matches = (
        [max(iou(c, ref) for ref in review.references) for c in intervals]
        if review.references
        else []
    )
    return {
        "analysis_id": review.analysis_id,
        "split": review.split,
        "evaluation_status": "complete" if complete else "incomplete",
        "candidate_count": len(ids),
        "rated_count": len(rated),
        "usable_count": sum(r.usable for r in rated),
        "usable_fraction": sum(r.usable for r in rated) / len(ids) if complete else None,
        "mean_boundaries": sum(r.boundaries for r in review.ratings) / len(ids)
        if complete
        else None,
        "mean_independence": sum(r.independence for r in review.ratings) / len(ids)
        if complete
        else None,
        "mean_best_reference_iou": sum(matches) / len(matches) if matches else None,
        "config": snapshot.get("config"),
        "policy_version": review.policy_version,
        "evaluation_input": frozen,
        "snapshot_sha256": fingerprint(snapshot),
        "selected_ids": [r.candidate_id for r in review.ratings if r.selected is True],
        "uncertain_count": sum(r.uncertain for r in review.ratings),
        "unreviewed_count": sum(r.usable is None and not r.uncertain for r in review.ratings),
        "feedback": [r.model_dump() for r in review.ratings],
        "cost": None,
        "limitations": (
            "사람 평가 기준선이며 품질 합격 판정이 아닙니다. "
            "비용은 별도 사용량 기록으로 확인합니다."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="추천 품질 평가 준비·조회·집계 (유료 호출 없음)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    capture = commands.add_parser("capture")
    capture.add_argument("analysis_id", type=UUID)
    capture.add_argument("--base-url", default="http://localhost:8000")
    capture.add_argument("--split", choices=["development", "holdout"], required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--source", type=Path, help="Local original; enables frozen input capture")
    report = commands.add_parser("report")
    report.add_argument("directory", type=Path)
    report.add_argument("--review", type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "preflight":
        from app.config import get_settings

        settings = get_settings()
        print(
            json.dumps(
                {
                    "paid_ai_enabled": settings.enable_paid_ai,
                    "free_ai_enabled": settings.enable_free_ai,
                    "transcription_provider": settings.transcription_provider,
                    "recommendation_provider": settings.recommendation_provider,
                    "groq_free_tier_confirmed": settings.groq_free_tier_confirmed,
                    "groq_key_configured": bool(settings.groq_api_key.get_secret_value()),
                    "azure_endpoint_configured": bool(settings.azure_speech_endpoint),
                    "azure_key_configured": bool(settings.azure_speech_key.get_secret_value()),
                    "openai_key_configured": bool(settings.openai_api_key.get_secret_value()),
                    "provider_auth_verified": False,
                }
            )
        )
    elif args.command == "capture":
        if args.output.exists():
            raise ValueError("새 평가 디렉토리를 지정하세요. 기존 결과는 덮어쓰지 않습니다.")
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.get(f"{args.base_url.rstrip('/')}/analyses/{args.analysis_id}")
            response.raise_for_status()
            snapshot = response.json()
            if args.source:
                from app.adapters.media import probe
                from app.services.video import checksum

                response = client.get(
                    f"{args.base_url.rstrip('/')}/analyses/{args.analysis_id}/transcript"
                )
                response.raise_for_status()
                transcript = response.json()
                if (
                    transcript["analysis_id"] != str(args.analysis_id)
                    or transcript["asset_id"] != snapshot["asset_id"]
                    or transcript["version"] != snapshot["config"]["asr_version"]
                ):
                    raise ValueError("전사와 분석이 일치하지 않습니다.")
                snapshot["evaluation_input"] = {
                    "source_sha256": checksum(args.source),
                    "duration_ms": int(probe(args.source).duration * 1000),
                    "transcript_sha256": fingerprint(transcript["segments"]),
                    "asr_version": transcript["version"],
                    "genre": snapshot["genre"],
                    "purpose": snapshot["purpose"],
                }
        if snapshot.get("status") != "succeeded" or snapshot.get("analysis_id") != str(
            args.analysis_id
        ):
            raise ValueError("지정한 분석이 완료되지 않았습니다.")
        review = Review(
            analysis_id=str(args.analysis_id),
            split=args.split,
            ratings=[Rating(candidate_id=c["id"]) for c in snapshot["candidates"]],
            snapshot_sha256=fingerprint(snapshot) if args.source else None,
        )
        save_new(args.output / "snapshot.json", snapshot)
        save_new(args.output / "review.json", review.model_dump())
        if args.source:
            save_new(args.output / "transcript.json", transcript)
        print("snapshot.json과 review.json을 저장했습니다. 사람 평가 후 report를 실행하세요.")
    elif args.command == "compare":
        from app.domain.recommendation_loop import compare_reports

        before, after = [
            json.loads(p.read_text(encoding="utf-8")) for p in (args.before, args.after)
        ]
        save_new(args.output, compare_reports(before, after))
    else:
        snapshot = json.loads((args.directory / "snapshot.json").read_text(encoding="utf-8"))
        review = Review.model_validate_json(
            (args.review or args.directory / "review.json").read_text(encoding="utf-8")
        )
        save_new(args.directory / "report.json", summarize(snapshot, review))
        print("report.json을 저장했습니다. incomplete는 품질 측정 완료가 아닙니다.")


if __name__ == "__main__":
    main()
