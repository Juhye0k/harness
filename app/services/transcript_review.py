"""Read saved transcripts and persist human decisions without provider calls."""

from app.domain.jobs import JobError
from app.domain.transcript_review import VERSION, inspect


def transcript(repo, analysis_id):
    job = repo.get(analysis_id)
    if job.status != "succeeded":
        raise JobError("RESULT_NOT_READY", "완료된 전사만 검수할 수 있습니다.", 409)
    return job, repo.read_transcript(job.asset_id, job.config["asr_version"])


def report(repo, analysis_id):
    job, segments = transcript(repo, analysis_id)
    data = inspect(segments)
    decisions = repo.review_decisions(job.id, job.config["asr_version"], VERSION)
    for row in data["segments"]:
        if row["id"] in decisions:
            row.update(decisions[row["id"]])
    return {
        "analysis_id": str(job.id),
        "transcript_version": job.config["asr_version"],
        **data,
        "unreviewed": sum(r["decision"] is None for r in data["segments"]),
    }


def decide(repo, analysis_id, segment_id, body):
    job, segments = transcript(repo, analysis_id)
    if segment_id not in {s["id"] for s in segments}:
        raise JobError("SEGMENT_NOT_FOUND", "전사 구간을 찾을 수 없습니다.", 404)
    if body.transcript_version != job.config["asr_version"] or body.policy_version != VERSION:
        raise JobError("REVIEW_VERSION_CONFLICT", "검수 버전을 새로 조회하세요.", 409)
    return repo.save_review(job.id, body.transcript_version, VERSION, segment_id, body)
