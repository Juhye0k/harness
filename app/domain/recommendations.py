"""Deterministic validation and ranking. Model output never controls tools or paths."""

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.subtitles import validate_words
from app.domain.transcript_review import quality
from app.domain.video import VideoError

VERSION = "text-v1"
WEIGHTS = {
    "hook": 25,
    "completeness": 25,
    "context_independence": 20,
    "memorable": 20,
    "editability": 10,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Segment(StrictModel):
    id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1)


class Proposal(StrictModel):
    start_segment_id: str
    end_segment_id: str
    title: str = Field(min_length=1, max_length=160)


class Proposals(StrictModel):
    candidates: list[Proposal] = Field(max_length=15)


class Score(StrictModel):
    candidate_id: str
    hook: int = Field(ge=0, le=4)
    completeness: int = Field(ge=0, le=4)
    context_independence: int = Field(ge=0, le=4)
    memorable: int = Field(ge=0, le=4)
    editability: int = Field(ge=0, le=4)
    reason: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)
    topic: str = Field(min_length=1, max_length=80)


class Scores(StrictModel):
    scores: list[Score] = Field(max_length=15)


def invalid():
    return VideoError("MODEL_RESPONSE_INVALID", "분석 응답이 계약을 지키지 않았습니다.")


def normalize(raw: dict, duration_ms: int) -> list[dict]:
    try:
        phrases = raw["phrases"]
        if not isinstance(phrases, list):
            raise ValueError()
        if len(phrases) > 2000:
            raise VideoError("TRANSCRIPT_LIMIT", "전사 입력 제한을 초과했습니다.")
        result = []
        last = -1
        last_end = -1
        last_word_end = -1
        for phrase in phrases:
            if not isinstance(phrase["text"], str):
                raise ValueError()
            if not phrase["text"].strip():
                continue
            start = phrase["offsetMilliseconds"]
            end = start + phrase["durationMilliseconds"]
            segment = Segment(
                id=f"s{len(result):04d}", start_ms=start, end_ms=end, text=phrase["text"].strip()
            )
            if start < last or end < last_end or end <= start or end > duration_ms:
                raise ValueError()
            last = start
            last_end = end
            normalized = segment.model_dump()
            if metrics := quality(phrase.get("quality")):
                normalized["quality"] = metrics
            if raw.get("_normalized_word_timestamps") is True:
                normalized["words"] = phrase["words"]
                validate_words(normalized)
                if normalized["words"][0]["start_ms"] < last_word_end:
                    raise ValueError()
                last_word_end = normalized["words"][-1]["end_ms"]
            result.append(normalized)
        if sum(len(s["text"]) for s in result) > 60000:
            raise VideoError("TRANSCRIPT_LIMIT", "전사 입력 제한을 초과했습니다.")
        return result
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise invalid() from exc


def candidates(raw: dict, segments: list[dict], duration_ms: int) -> tuple[list, list]:
    try:
        proposals = Proposals.model_validate(raw).candidates
    except ValidationError as exc:
        raise invalid() from exc
    indices = {s["id"]: i for i, s in enumerate(segments)}
    valid, rejected = [], []
    for index, proposal in enumerate(proposals):
        try:
            first, last = indices[proposal.start_segment_id], indices[proposal.end_segment_id]
            if first > last:
                raise ValueError()
            start, end = segments[first]["start_ms"], segments[last]["end_ms"]
            if not 30000 <= end - start <= 60000:
                raise ValueError()
            padding = min(200, (60000 - (end - start)) // 2)
            start, end = max(0, start - padding), min(duration_ms, end + padding)
            valid.append(
                {
                    "id": f"c{index:02d}",
                    "start_ms": start,
                    "end_ms": end,
                    "title": proposal.title,
                    "segments": segments[first : last + 1],
                }
            )
        except (KeyError, ValueError):
            rejected.append({"index": index, "reason": "INVALID_RANGE_OR_SEGMENT"})
    if proposals and not valid:
        raise invalid()
    return valid, rejected


def rank(raw: dict, proposals: list[dict]) -> list[dict]:
    try:
        scores = Scores.model_validate(raw).scores
    except ValidationError as exc:
        raise invalid() from exc
    by_id = {c["id"]: c for c in proposals}
    if len(scores) != len(by_id) or {s.candidate_id for s in scores} != set(by_id):
        raise invalid()
    eligible = []
    for score in scores:
        candidate = by_id[score.candidate_id]
        if not set(score.evidence_ids) <= {s["id"] for s in candidate["segments"]}:
            raise invalid()
        if score.completeness < 2 or score.context_independence < 2:
            continue
        metrics = {key: getattr(score, key) for key in WEIGHTS}
        eligible.append(
            {
                **candidate,
                "scores": metrics,
                "score": sum(WEIGHTS[k] * metrics[k] / 4 for k in WEIGHTS),
                "reason": score.reason,
                "evidence_ids": score.evidence_ids,
                "topic": score.topic,
            }
        )
    selected, topics = [], {}
    for item in sorted(eligible, key=lambda c: (-c["score"], c["start_ms"], c["id"])):
        if topics.get(item["topic"], 0) >= 2:
            continue
        if any(
            max(0, min(item["end_ms"], other["end_ms"]) - max(item["start_ms"], other["start_ms"]))
            / min(item["end_ms"] - item["start_ms"], other["end_ms"] - other["start_ms"])
            >= 0.5
            for other in selected
        ):
            continue
        selected.append(item)
        topics[item["topic"]] = topics.get(item["topic"], 0) + 1
        if len(selected) == 5:
            break
    return selected
