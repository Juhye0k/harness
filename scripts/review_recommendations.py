"""Loopback-only manual review UI over a frozen private evaluation directory."""

import argparse
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict

from scripts.evaluate_recommendations import Review, fingerprint, save_new, summarize


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str | None = None
    review: Review


def create_app(directory: Path, source: Path):
    directory, source = directory.resolve(), source.resolve()
    snapshot = json.loads((directory / "snapshot.json").read_text(encoding="utf-8"))
    initial = Review.model_validate_json((directory / "review.json").read_text(encoding="utf-8"))
    from app.adapters.media import probe
    from app.services.video import checksum

    frozen = snapshot.get("evaluation_input")
    if not frozen or checksum(source) != frozen["source_sha256"]:
        raise ValueError("원본 영상과 평가 입력이 일치하지 않습니다.")
    if abs(int(probe(source).duration * 1000) - frozen["duration_ms"]) > 100:
        raise ValueError("영상 길이가 평가 입력과 다릅니다.")
    summarize(snapshot, initial)
    transcript = json.loads((directory / "transcript.json").read_text(encoding="utf-8"))
    if fingerprint(transcript["segments"]) != frozen["transcript_sha256"]:
        raise ValueError("전사 고정본이 변경되었습니다.")
    from app.domain.subtitles import build_subtitles

    subtitles = build_subtitles(transcript["segments"])
    reviews = directory / "web-reviews"
    reviews.mkdir(exist_ok=True)
    lock = threading.Lock()
    app = FastAPI(title="추천 수작업 평가", docs_url=None, redoc_url=None)

    def latest():
        entries = sorted(reviews.glob("*/review.json"))
        if not entries:
            return None, initial.model_dump()
        path = entries[-1]
        return path.parent.name, json.loads(path.read_text(encoding="utf-8"))

    @app.middleware("http")
    async def private(request, call_next):
        if request.headers.get("host", "").split(":")[0] not in {
            "127.0.0.1",
            "localhost",
            "testserver",
        }:
            return HTMLResponse("Local access only", status_code=403)
        if request.method == "POST" and request.headers.get("origin") not in (
            None,
            str(request.base_url).rstrip("/"),
        ):
            return HTMLResponse("Origin mismatch", status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/", response_class=HTMLResponse)
    def index():
        return Path(__file__).with_suffix(".html").read_text(encoding="utf-8")

    @app.get("/api/review")
    def get_review():
        with lock:
            revision, review = latest()
            report = summarize(snapshot, Review.model_validate(review))
        return {
            "snapshot": snapshot,
            "review": review,
            "revision": revision,
            "report": report,
            "transcript": transcript["segments"],
            "subtitles": subtitles,
        }

    @app.get("/media")
    def media():
        return FileResponse(source)

    @app.post("/api/review")
    def save_review(body: Submission):
        try:
            if any(r.end_ms > frozen["duration_ms"] for r in body.review.references):
                raise ValueError("기준 구간이 원본 범위를 초과했습니다.")
            if (
                body.review.policy_version != initial.policy_version
                or body.review.split != initial.split
            ):
                raise ValueError("평가 기준과 데이터 구분은 변경할 수 없습니다.")
            report = summarize(snapshot, body.review)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        with lock:
            revision, _ = latest()
            if revision != body.revision:
                raise HTTPException(409, "다른 탭에서 저장했습니다. 다시 불러오세요.")
            name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid4().hex[:8]
            target = reviews / name
            target.mkdir()
            issues = []
            for rating in body.review.ratings:
                if rating.usable is False or rating.edited_range:
                    severity = "minor" if set(rating.reasons) <= {"preference"} else "major"
                    issues.append(
                        {
                            "id": "candidate-" + str(len(issues) + 1),
                            "severity": severity,
                            "verification": "human",
                            "description": rating.notes or ", ".join(rating.reasons),
                            "evidence": f"candidate={rating.candidate_id}; "
                            f"snapshot={fingerprint(snapshot)}",
                            "hypothesis": "미확인",
                            "proposed_fix": "사람 피드백을 근거로 원인 확인 후 수정",
                        }
                    )
            handoff = {
                "schema_version": "manual-review-v1",
                "status": "ready_for_analysis"
                if report["evaluation_status"] == "complete"
                else "waiting_human",
                "snapshot_sha256": fingerprint(snapshot),
                "issues": issues,
                "external_calls_authorized": False,
                "next_action": "원인 확인 → 회귀 검사 → 수정 → 같은 전사로 재검증",
                "quality_pass": None,
            }
            for filename, data in (
                ("snapshot.json", snapshot),
                ("report.json", report),
                ("review.json", body.review.model_dump()),
                ("handoff.json", handoff),
            ):
                save_new(target / filename, data)
            if report["evaluation_status"] == "complete":
                from scripts.recommendation_loop import Policy, append, baseline_files, code_hash

                policy = Policy(
                    checks={
                        "basic": ["uv", "run", "python", "scripts/verify.py"],
                        "integration": [
                            "docker",
                            "compose",
                            "-f",
                            "compose.integration.yaml",
                            "run",
                            "--rm",
                            "runner",
                        ],
                    },
                    issues=issues,
                ).model_dump()
                session = {
                    "policy": policy,
                    "protected_files": baseline_files(),
                    "initial_source_sha256": code_hash(),
                }
                session_directory = target / "loop"
                save_new(session_directory / "session.json", session)
                append(
                    session_directory,
                    session,
                    [],
                    {
                        "kind": "evaluation",
                        "report": report,
                        "source_sha256": code_hash(),
                        "summary": "웹에서 저장한 사람 평가",
                    },
                )
        return {"revision": name, "report": report, "handoff": handoff}

    @app.get("/api/download/{kind}")
    def download(kind: str):
        if kind not in {"review", "report", "handoff"}:
            raise HTTPException(404)
        with lock:
            revision, _ = latest()
            if revision is None:
                raise HTTPException(409, "먼저 평가를 저장하세요.")
        return FileResponse(reviews / revision / f"{kind}.json", filename=f"{kind}.json")

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    uvicorn.run(create_app(args.directory, args.source), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
