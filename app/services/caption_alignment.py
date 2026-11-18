"""Prepare optional editor drafts inside the existing analysis worker."""

from app.adapters.caption_observations import read_caption_observations
from app.domain.caption_edit import validate_cues
from app.domain.shorts_subtitles import build_shorts
from app.domain.source_caption_evaluation import screen_transitions
from app.domain.source_caption_proposal import propose_from_transcript
from app.domain.video import VideoError

ALIGNMENT_VERSION = "persistent-ocr-transcript-v1"


def align_candidate_captions(root, asset, segments, candidates):
    if not candidates:
        return
    try:
        observation = read_caption_observations(root, asset)
    except (OSError, AttributeError, KeyError, TypeError, ValueError):
        for candidate in candidates:
            candidate["caption_draft"] = {"status": "alignment_needs_review"}
        return
    by_id = {segment["id"]: segment for segment in segments}
    for candidate in candidates:
        source_segments = [by_id[s["id"]] for s in candidate["segments"]]
        candidate["caption_draft"] = aligned_draft(observation, candidate, source_segments)


def aligned_draft(observation, candidate, segments):
    if observation is None:
        return {"status": "observations_unavailable"}
    start, end = candidate["start_ms"], candidate["end_ms"]
    frames = observation["frames"]
    sample_step = observation["sample_step_ms"]
    if frames[0]["time_ms"] > start or frames[-1]["time_ms"] + sample_step < end:
        return {"status": "observations_unavailable"}
    try:
        if sum(len(segment.get("words", [])) for segment in segments) > 1000:
            raise ValueError("Candidate exceeds alignment word budget")
        tolerance, changes = screen_transitions(observation, start, end)
        cues, boundaries, cut = propose_from_transcript(segments, start, end, changes, tolerance)
        if not boundaries or not 1 <= len(cues) <= 200:
            raise ValueError("No usable transitions and complete readable partition")
        cues = validate_cues(cues, segments, start, end, reviewed=False)
    except (VideoError, KeyError, TypeError, ValueError):
        return {"status": "alignment_needs_review"}
    return {"status": "aligned", "cues": cues, "cut_words": cut}


def editor_suggestion(candidate, segments):
    draft = candidate.get("caption_draft", {"status": "not_processed"})
    start, end = candidate["start_ms"], candidate["end_ms"]
    alignment = {"status": draft["status"]}
    if draft["status"] != "aligned":
        return build_shorts(segments, start, end), alignment

    alignment["cut_words"] = draft["cut_words"]
    alignment["version"] = ALIGNMENT_VERSION
    display = build_shorts([], start, end)
    display.update(
        alignment_version=ALIGNMENT_VERSION,
        cues=draft["cues"],
        coverage_complete=draft["cut_words"] == 0,
        quality_pass=True,
        review_required=True,
        source_segments=len(segments),
        ready_segments=len({cue["source_segment_id"] for cue in draft["cues"]}),
        source_characters=sum(len("".join(segment["text"].split())) for segment in segments),
    )
    return display, alignment
