"""Private local repair/check loop. Commands are explicit argv, never shell strings.

No built-in AI client. A user-configured coding worker receives a task on stdin;
the harness executes checks itself. This orchestrator is not a permission sandbox.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.process import run
from app.domain.recommendation_loop import Issue, decide
from app.domain.video import VideoError
from scripts.evaluate_recommendations import Review, fingerprint, save_new, summarize

ROOT = Path(__file__).resolve().parents[1]


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    checks: dict[str, list[str]]
    issues: list[Issue]
    worker: list[str] = Field(default_factory=list)
    command_timeout_seconds: int = Field(default=1800, ge=1, le=7200)

    @model_validator(mode="after")
    def valid_commands(self):
        if not {"basic", "integration"} <= self.checks.keys():
            raise ValueError("basic and integration checks are required")
        if len({i.id for i in self.issues}) != len(self.issues):
            raise ValueError("Duplicate issue ID")
        for issue in self.issues:
            if issue.verification == "regression" and issue.check not in self.checks:
                raise ValueError("Unknown regression check")
        for argv in [*self.checks.values(), *([self.worker] if self.worker else [])]:
            if not argv or any(not isinstance(arg, str) or not arg for arg in argv):
                raise ValueError("Commands must be nonempty argv arrays")
        return self


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def code_hash():
    paths = []
    for directory in ("app", "scripts", "tests", "migrations"):
        paths.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    paths.extend(ROOT / name for name in ("pyproject.toml", "uv.lock", "compose.integration.yaml"))
    return fingerprint(
        {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)
        }
    )


def baseline_files():
    # Existing acceptance tests and harness cannot silently be weakened by a repair worker.
    paths = list((ROOT / "tests").rglob("*.py")) + [
        Path(__file__),
        ROOT / "scripts/evaluate_recommendations.py",
        ROOT / "app/domain/recommendation_loop.py",
        ROOT / "scripts/verify.py",
        ROOT / "AGENTS.md",
    ]
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }


def load(directory):
    session = read(directory / "session.json")
    Policy.model_validate(session["policy"])
    events = [read(p) for p in sorted(directory.glob("event-*.json"))]
    for index, event in enumerate(events):
        if event["sequence"] != index or event["session_sha256"] != fingerprint(session):
            raise ValueError("Event history does not match session")
        expected = fingerprint(events[index - 1]) if index else None
        if event["previous_sha256"] != expected:
            raise ValueError("Broken event history")
    return session, events


def append(directory, session, history, event):
    event = {
        **event,
        "sequence": len(history),
        "recorded_at": datetime.now(UTC).isoformat(),
        "session_sha256": fingerprint(session),
        "previous_sha256": fingerprint(history[-1]) if history else None,
    }
    save_new(directory / f"event-{len(history):06d}.json", event)
    history.append(event)


def integrity(session, directory):
    if read(directory / "session.json") != session:
        raise ValueError("Session policy changed; prepare a new reviewed session")
    for name, digest in session["protected_files"].items():
        path = ROOT / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Protected acceptance files changed; human review required")


def state(session, events):
    approvals = {e["issue_id"]: e["source_sha256"] for e in events if e["kind"] == "human"}
    return decide(session["policy"], events, code_hash(), approvals)


def execute(argv, timeout, payload=None):
    try:
        run(argv, timeout, input_text=json.dumps(payload) if payload else None)
        return {"passed": True, "error": None}
    except VideoError as exc:
        return {"passed": False, "error": exc.code}


def check(directory, session, events, deadline):
    started = code_hash()
    results = {}
    for name, argv in session["policy"]["checks"].items():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        results[name] = execute(argv, min(remaining, session["policy"]["command_timeout_seconds"]))
    integrity(session, directory)
    passed = (
        len(results) == len(session["policy"]["checks"])
        and all(r["passed"] for r in results.values())
        and started == code_hash()
    )
    append(
        directory,
        session,
        events,
        {"kind": "check", "source_sha256": started, "passed": passed, "results": results},
    )


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--policy", type=Path, required=True)
    init.add_argument("--output", type=Path, required=True)
    for name in ("status", "check", "run", "confirm-human", "record-evaluation"):
        sub = commands.add_parser(name)
        sub.add_argument("directory", type=Path)
        if name in ("check", "run"):
            sub.add_argument("--seconds", type=int, required=True)
        if name == "confirm-human":
            sub.add_argument("--issue", required=True)
            sub.add_argument("--source-sha256", required=True)
            sub.add_argument("--reviewer", required=True)
            sub.add_argument("--evidence", required=True)
        if name == "record-evaluation":
            sub.add_argument("--evaluation", type=Path, required=True)
            sub.add_argument("--summary", required=True)
    args = parser.parse_args(argv)
    if args.command == "init":
        policy = Policy.model_validate(read(args.policy)).model_dump()
        args.output.mkdir(parents=True, exist_ok=False)
        save_new(
            args.output / "session.json",
            {
                "policy": policy,
                "protected_files": baseline_files(),
                "initial_source_sha256": code_hash(),
            },
        )
        return 0
    session, events = load(args.directory)
    integrity(session, args.directory)
    if args.command == "record-evaluation":
        snapshot = read(args.evaluation / "snapshot.json")
        review = Review.model_validate(read(args.evaluation / "review.json"))
        report = summarize(snapshot, review)
        if not report["evaluation_input"]:
            raise ValueError("Frozen source and transcript required")
        previous = [e for e in events if e["kind"] == "evaluation"]
        if previous:
            from app.domain.recommendation_loop import compare_reports

            compare_reports(previous[-1]["report"], report)
        append(
            args.directory,
            session,
            events,
            {
                "kind": "evaluation",
                "source_sha256": code_hash(),
                "summary": args.summary,
                "report": report,
            },
        )
    elif args.command == "confirm-human":
        if not args.reviewer.strip() or not args.evidence.strip():
            raise ValueError("Human reviewer and evidence required")
        issue = next((i for i in session["policy"]["issues"] if i["id"] == args.issue), None)
        if not issue or issue["verification"] != "human" or args.source_sha256 != code_hash():
            raise ValueError("Unknown human issue or stale source hash")
        append(
            args.directory,
            session,
            events,
            {
                "kind": "human",
                "issue_id": args.issue,
                "source_sha256": args.source_sha256,
                "reviewer": args.reviewer,
                "evidence": args.evidence,
            },
        )
    elif args.command in ("check", "run"):
        if args.seconds <= 0:
            raise ValueError("Positive execution time allowance required")
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            check(args.directory, session, events, deadline)
            current = state(session, events)
            if current["status"] in ("complete", "waiting_human") or args.command == "check":
                break
            if current["status"] == "needs_check":
                continue
            worker = session["policy"]["worker"]
            if not worker:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            failures = [e for e in events if e["kind"] == "check" and not e["passed"]]
            task = {
                "issues": session["policy"]["issues"],
                "checks": session["policy"]["checks"],
                "last_check": events[-1],
                "change_approach": len(failures) >= 2,
                "constraints": "Offline repairs only. No AI/provider calls, publish, commit, "
                "human decisions, acceptance-test weakening or policy changes.",
            }
            result = execute(
                worker, min(remaining, session["policy"]["command_timeout_seconds"]), task
            )
            integrity(session, args.directory)
            append(
                args.directory,
                session,
                events,
                {"kind": "worker", **result, "source_sha256": code_hash()},
            )
            if not result["passed"]:
                break
    result = state(session, events)
    result["source_sha256"] = code_hash()
    if args.command == "run" and result["status"] != "complete":
        result["execution_status"] = (
            "waiting_human"
            if result["status"] == "waiting_human"
            else "incomplete_check_budget_or_worker"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    mutations = {"check", "run", "confirm-human", "record-evaluation"}
    if len(argv) < 2 or argv[0] not in mutations:
        return _main(argv)
    lock = Path(argv[1]) / "execution.lock"
    # Interrupted sessions require an operator to confirm the worker has stopped
    # before removing the lock. Never auto-resume a possibly running repair.
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(time.time()))
    try:
        return _main(argv)
    finally:
        lock.unlink()


if __name__ == "__main__":
    sys.exit(main())
