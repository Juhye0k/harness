"""Compare against sampled screen captions, never against claimed human/audio truth."""

import math
import re
from collections import Counter

from app.domain.transcript_evaluation import edit_distance, normalize_text, ratio

VERSION = "source-caption-evaluation-v1"


def references(observation, start_ms, end_ms, fold):
    if fold not in (0, 1) or not 0 <= start_ms < end_ms:
        raise ValueError("Invalid range or fold")
    step = observation.get("sample_step_ms")
    frames = observation.get("frames")
    if type(step) is not int or not 20 <= step <= 1000 or not frames or len(frames) > 10000:
        raise ValueError("Invalid sampling manifest")
    for index, frame in enumerate(frames):
        if (
            type(frame.get("time_ms")) is not int
            or frame["time_ms"] < 0
            or not isinstance(frame.get("text"), str)
            or len(frame["text"]) > 1000
            or (index and frame["time_ms"] - frames[index - 1]["time_ms"] != step)
        ):
            raise ValueError("Invalid or missing frame observations")
    groups = []
    for frame in frames[fold::2]:
        normalized = normalize_text(frame["text"])
        similar = (
            bool(groups)
            and bool(normalized)
            and bool(groups[-1]["normalized"])
            and (
                edit_distance(groups[-1]["normalized"], normalized) * 10
                <= max(len(groups[-1]["normalized"]), len(normalized))
            )
        )
        if groups and (groups[-1]["normalized"] == normalized or similar):
            groups[-1]["end_ms"] = frame["time_ms"] + step * 2
            groups[-1]["samples"] += 1
            groups[-1]["texts"].append(frame["text"])
            groups[-1]["confidence"].append(frame.get("confidence"))
        else:
            groups.append(
                {
                    "start_ms": frame["time_ms"],
                    "end_ms": frame["time_ms"] + step * 2,
                    "normalized": normalized,
                    "samples": 1,
                    "texts": [frame["text"]],
                    "confidence": [frame.get("confidence")],
                }
            )
    cues, blocked = [], []
    for group in groups:
        if group["end_ms"] <= start_ms or group["start_ms"] >= end_ms:
            continue
        votes = Counter(normalize_text(text) for text in group["texts"])
        winner, count = votes.most_common(1)[0]
        text = " ".join(next(t for t in group["texts"] if normalize_text(t) == winner).split())
        scores = [score for score in group["confidence"] if score is not None]
        if any(type(score) not in (int, float) or not 0 <= score <= 100 for score in scores):
            raise ValueError("Invalid OCR confidence")
        row = {
            "start_ms": max(start_ms, group["start_ms"]),
            "end_ms": min(end_ms, group["end_ms"]),
            "text": text,
            "samples": group["samples"],
            "boundary_uncertainty_ms": step * 2,
            "consensus_ratio": count / group["samples"],
            "ocr_confidence": sum(scores) / len(scores) if scores else None,
        }
        if not group["normalized"] or group["samples"] < 2:
            blocked.append({**row, "reason": "NO_REFERENCE" if not text else "UNSTABLE_OCR"})
        elif row["consensus_ratio"] < 0.6 or (scores and row["ocr_confidence"] < 70):
            blocked.append({**row, "reason": "OCR_UNCERTAIN"})
        elif group["start_ms"] < start_ms or group["end_ms"] > end_ms:
            blocked.append({**row, "reason": "REFERENCE_CROSSES_CANDIDATE_BOUNDARY"})
        else:
            cues.append(row)
    coverage = sum(c["end_ms"] - c["start_ms"] for c in cues)
    return {
        "fold": fold,
        "cues": cues,
        "blocked": blocked,
        "reference_coverage_ms": coverage,
        "reference_coverage_ratio": coverage / (end_ms - start_ms),
        "human_verified": False,
        "audio_accuracy_verified": False,
        "reference_kind": "machine_observed_burned_in_captions",
    }


def cue_text(cue):
    return " ".join(cue["lines"]) if "lines" in cue else cue["text"]


def evaluate(reference, cues):
    rows = reference["cues"]
    # Exclude intervals without an independent screen reference, in BOTH inputs.
    selected = []
    used = set()
    for index, cue in enumerate(cues):
        start, end = cue["start_ms"], cue["end_ms"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end:
            raise ValueError("Invalid hypothesis timing")
        middle = (start + end) / 2
        if any(row["start_ms"] <= middle < row["end_ms"] for row in rows):
            selected.append(cue)
            used.add(index)
    expected = normalize_text("".join(row["text"] for row in rows))
    actual = normalize_text("".join(cue_text(row) for row in selected))
    distance = edit_distance(expected, actual)
    temporal = []
    empty = 0
    for row in rows:
        overlapping = [
            cue
            for cue in cues
            if cue["end_ms"] > row["start_ms"] and cue["start_ms"] < row["end_ms"]
        ]
        if not overlapping:
            empty += 1
            continue
        candidates = [
            cue
            for cue in overlapping
            if normalize_text(cue_text(cue)) in normalize_text(row["text"])
            and normalize_text(cue_text(cue))
        ]
        if candidates:
            temporal.append(max(0, row["start_ms"] - min(c["start_ms"] for c in candidates)))
    return {
        "reference_characters": len(expected),
        "hypothesis_characters": len(actual),
        "character_edits": distance,
        "screen_reference_cer": ratio(distance, len(expected)),
        "compared_cues": len(selected),
        "unscored_cues": len(cues) - len(used),
        "reference_intervals_without_any_caption": empty,
        "early_onset_ms_on_contained_text": temporal,
        "human_audio_cer": None,
        "quality_pass": None,
        "scope": "agreement_with_visible_subtitles_on_reference_available_intervals",
    }


def frame_agreement(observation, proposed, start_ms, end_ms, fold=1):
    compared = matched = unknown = 0
    for index, frame in enumerate(observation["frames"]):
        if index % 2 != fold or not start_ms <= frame["time_ms"] < end_ms:
            continue
        expected = normalize_text(frame["text"])
        if not expected:
            unknown += 1
            continue
        actual = normalize_text(
            "".join(
                cue_text(c) for c in proposed if c["start_ms"] <= frame["time_ms"] < c["end_ms"]
            )
        )
        compared += 1
        matched += expected == actual
    return {
        "fold": fold,
        "compared_nonempty_frames": compared,
        "exact_agreement_frames": matched,
        "agreement_ratio": ratio(matched, compared),
        "unknown_reference_frames": unknown,
        "scope": "held_out_from_cue_reconstruction_not_an_independent_video_test_set",
    }


def policy_violations(cues):
    counts = Counter()
    previous = 0
    for cue in cues:
        duration = cue["end_ms"] - cue["start_ms"]
        text = cue_text(cue)
        lines = cue.get("lines", [text])
        if not 450 <= duration <= 1800:
            counts["duration"] += 1
        if not 1 <= len(text.split()) <= 3:
            counts["eojeol"] += 1
        if len(lines) > 2 or any(len(line) > 14 for line in lines):
            counts["line_length"] += 1
        if duration <= 0 or not math.isfinite(duration) or len(text) * 1000 > duration * 15:
            counts["reading_speed"] += 1
        if cue["start_ms"] < previous:
            counts["overlap"] += 1
        previous = cue["end_ms"]
    return dict(counts)


def fixed_screen_reference(data, observation, start_ms, end_ms):
    if (
        data.get("source_sha256") != observation["source_sha256"]
        or data.get("reference_kind") != "agent_visual_screen_labels"
        or data.get("human_verified") is not False
    ):
        raise ValueError("Invalid fixed screen reference provenance")
    frame_evidence = {(row["time_ms"], row.get("frame_sha256")) for row in observation["frames"]}
    previous = start_ms
    cues = data["cues"]
    for cue in cues:
        if (
            not previous <= cue["start_ms"] < cue["end_ms"] <= end_ms
            or not isinstance(cue["text"], str)
            or not normalize_text(cue["text"])
            or not cue["start_ms"] <= cue["evidence_time_ms"] < cue["end_ms"]
            or (cue["evidence_time_ms"], cue["evidence_frame_sha256"]) not in frame_evidence
        ):
            raise ValueError("Screen label does not match its source frame or range")
        previous = cue["end_ms"]
    duration = sum(c["end_ms"] - c["start_ms"] for c in cues)
    return {
        "reference_kind": data["reference_kind"],
        "cues": cues,
        "reference_coverage_ms": duration,
        "reference_coverage_ratio": duration / (end_ms - start_ms),
        "blocked": data.get("unavailable", []),
        "human_verified": False,
        "audio_accuracy_verified": False,
    }


def decision(baseline, proposal):
    reasons = []
    if baseline["screen_reference_cer"] is None or proposal["screen_reference_cer"] is None:
        reasons.append("NO_STABLE_REFERENCE")
    elif proposal["screen_reference_cer"] >= baseline["screen_reference_cer"]:
        reasons.append("CONTENT_NOT_IMPROVED")
    if proposal["policy_violations"]:
        reasons.append("READABILITY_POLICY")
    return {
        "action": "keep_existing" if reasons else "experimental_draft_only",
        "reasons": reasons,
        "production_approval": False,
        "human_audio_confirmation": False,
    }


def compare(observation, editor, fixed_reference=None, proposed_cues=None):
    fingerprint = observation.get("source_sha256", "")
    if (
        not isinstance(fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        or fingerprint != editor.get("source_sha256")
        or observation.get("schema_version") != "source-caption-ocr-v1"
    ):
        raise ValueError("Original video fingerprint mismatch")
    training = references(observation, editor["start_ms"], editor["end_ms"], 0)
    validation = references(observation, editor["start_ms"], editor["end_ms"], 1)
    if fixed_reference is not None:
        validation = fixed_screen_reference(
            fixed_reference, observation, editor["start_ms"], editor["end_ms"]
        )
    baseline = editor["latest_revision"]["cues"]
    draft = training["cues"] if proposed_cues is None else proposed_cues
    result = {
        "version": VERSION,
        "source_sha256": editor["source_sha256"],
        "analysis_id": editor["analysis_id"],
        "candidate_id": editor["candidate_id"],
        "revision_id": editor["latest_revision"]["revision_id"],
        "reference": {k: v for k, v in validation.items() if k != "cues"},
        "baseline": {
            **evaluate(validation, baseline),
            "policy_violations": policy_violations(baseline),
        },
        "screen_draft": {
            **evaluate(validation, draft),
            "policy_violations": policy_violations(draft),
            "validation_frames": frame_agreement(
                observation, draft, editor["start_ms"], editor["end_ms"]
            ),
            "production_ready": False,
        },
        "reference_cues": validation["cues"],
        "proposed_cues": draft,
        "external_calls": 0,
        "human_review_changed": False,
        "limitation": (
            "Screen subtitles can omit or paraphrase speech; OCR agreement is not audio truth."
        ),
    }
    result["decision"] = decision(result["baseline"], result["screen_draft"])
    return result
