"""Offline comparison and convergence policy; no model or subprocess calls."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    severity: Literal["major", "minor"]
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    hypothesis: str = ""
    proposed_fix: str = ""
    verification: Literal["regression", "human"]
    check: str | None = None

    @model_validator(mode="after")
    def regression_required(self):
        if self.verification == "regression" and not self.check:
            raise ValueError("Regression issues require a named check")
        return self


def compare_reports(before, after):
    if not before.get("evaluation_input") or (
        before["evaluation_input"] != after.get("evaluation_input")
        or before["policy_version"] != after["policy_version"]
        or before["split"] != after["split"]
    ):
        raise ValueError("동일 입력·평가 기준·데이터 구분만 비교할 수 있습니다.")
    metrics = ("usable_fraction", "usable_count", "mean_boundaries", "mean_independence")
    return {
        "before": before["analysis_id"],
        "after": after["analysis_id"],
        "evaluation_input": before["evaluation_input"],
        "configs": [before["config"], after["config"]],
        "status": "complete"
        if all(r["evaluation_status"] == "complete" for r in (before, after))
        else "incomplete",
        "metrics": {
            key: {
                "before": before[key],
                "after": after[key],
                "delta": after[key] - before[key]
                if before[key] is not None and after[key] is not None
                else None,
            }
            for key in metrics
        },
        "feedback": {"before": before["feedback"], "after": after["feedback"]},
        "quality_pass": None,
        "cost": None,
    }


def decide(policy, history, source_hash, human_reviews):
    """Two full passes of identical code; human judgement is bound to those bytes."""
    recent = []
    for event in reversed(history):
        if event.get("kind") != "check":
            if event.get("kind") == "worker":
                break
            continue
        if event["source_sha256"] != source_hash or not event["passed"]:
            break
        recent.append(event)
    latest = history[-1] if history and history[-1].get("kind") == "check" else None
    human = [
        i["id"]
        for i in policy["issues"]
        if i["severity"] == "major"
        and i["verification"] == "human"
        and human_reviews.get(i["id"]) != source_hash
    ]
    failed = latest and latest["source_sha256"] == source_hash and not latest["passed"]
    if failed:
        return {"status": "needs_fix", "consecutive_passes": 0, "pending_human_issues": human}
    if human:
        return {"status": "waiting_human", "issues": human, "consecutive_passes": len(recent)}
    if len(recent) >= 2:
        status = "complete"
    else:
        status = "needs_check"
    return {
        "status": status,
        "consecutive_passes": len(recent),
        "minor_issues": [i for i in policy["issues"] if i["severity"] == "minor"],
    }
