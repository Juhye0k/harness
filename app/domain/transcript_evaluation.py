"""Offline quality evaluation. Unreviewed ASR output is never a reference."""

import hashlib
import json
import unicodedata

VERSION = "transcript-evaluation-v1"
NORMALIZATION = "unicode-nfc-casefold-alphanumeric-v1"


def fingerprint(report):
    bound = {key: report[key] for key in ("analysis_id", "transcript_version", "policy_version")}
    bound["segments"] = [
        {key: row[key] for key in ("id", "text", "start_ms", "end_ms")}
        for row in sorted(report["segments"], key=lambda row: row["id"])
    ]
    return hashlib.sha256(
        json.dumps(bound, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def normalize_text(text):
    return "".join(char for char in unicodedata.normalize("NFC", text).casefold() if char.isalnum())


def edit_distance(reference, hypothesis):
    # Only two rows of memory; never concatenate independent segment boundaries.
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def reference_template(report):
    return {
        "schema_version": VERSION,
        "report_sha256": fingerprint(report),
        "analysis_id": report["analysis_id"],
        "references": [
            {
                "segment_id": row["id"],
                "human_verified": False,
                "decision": "unreviewed",
                "reference_text": None,
            }
            for row in report["segments"]
        ],
    }


def compare_runs(report, previous):
    current = {row["id"]: row for row in report["segments"]}
    earlier = {row["id"]: row for row in previous["segments"]}
    shared = set(current) & set(earlier)
    text_changes = sorted(sid for sid in shared if current[sid]["text"] != earlier[sid]["text"])
    time_changes = sorted(
        sid
        for sid in shared
        if (current[sid]["start_ms"], current[sid]["end_ms"])
        != (earlier[sid]["start_ms"], earlier[sid]["end_ms"])
    )
    return {
        "comparison_kind": "run_agreement_not_accuracy",
        "previous_transcript_version": previous.get("version", previous.get("transcript_version")),
        "shared_segments": len(shared),
        "text_changed_ids": text_changes,
        "time_changed_ids": time_changes,
        "unmatched_current_ids": sorted(set(current) - set(earlier)),
        "unmatched_previous_ids": sorted(set(earlier) - set(current)),
    }


def evaluate(report, references=None):
    rows = {row["id"]: row for row in report["segments"]}
    if len(rows) != len(report["segments"]) or len(rows) > 2000:
        raise ValueError("Invalid or duplicate report segments")
    bound = fingerprint(report)
    references = references or reference_template(report)
    if (
        references.get("schema_version") != VERSION
        or references.get("report_sha256") != bound
        or references.get("analysis_id") != report["analysis_id"]
    ):
        raise ValueError("Reference version or transcript fingerprint mismatch")
    labels, corrections, seen = {}, {}, set()
    if len(references["references"]) > 2000:
        raise ValueError("Reference segment limit exceeded")
    for item in references["references"]:
        sid = item["segment_id"]
        if sid not in rows or sid in seen:
            raise ValueError("Unknown or duplicate reference segment")
        seen.add(sid)
        if type(item.get("human_verified")) is not bool:
            raise ValueError("human_verified must be boolean")
        decision = item.get("decision")
        if decision not in {"error", "ok", "uncertain", "unreviewed"}:
            raise ValueError("Invalid human decision")
        text = item.get("reference_text")
        if text is not None and (not isinstance(text, str) or len(text) > 5000):
            raise ValueError("Invalid reference text")
        if not item["human_verified"]:
            continue
        if decision in {"ok", "error"}:
            labels[sid] = decision
        if text is not None:
            corrections[sid] = text
    if sum(len(text) for text in corrections.values()) > 60000:
        raise ValueError("Reference character limit exceeded")
    distances, characters = 0, 0
    per_segment = []
    for sid, text in corrections.items():
        reference, hypothesis = normalize_text(text), normalize_text(rows[sid]["text"])
        distance = edit_distance(reference, hypothesis)
        characters += len(reference)
        distances += distance
        per_segment.append(
            {"segment_id": sid, "edits": distance, "reference_characters": len(reference)}
        )

    def detector(selected):
        tp = sum(label == "error" and sid in selected for sid, label in labels.items())
        fp = sum(label == "ok" and sid in selected for sid, label in labels.items())
        fn = sum(label == "error" and sid not in selected for sid, label in labels.items())
        tn = sum(label == "ok" and sid not in selected for sid, label in labels.items())
        full = bool(rows) and len(labels) == len(rows)
        return {
            "evaluated": len(labels),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
            "precision_on_reviewed": ratio(tp, tp + fp),
            "unflagged_error_rate_on_reviewed": ratio(fn, fn + tn),
            "recall": ratio(tp, tp + fn) if full else None,
            "recall_scope": "full_transcript" if full else "unavailable_partial_labels",
        }

    recognition = {sid for sid, row in rows.items() if row["recognition_reasons"]}
    queue = {sid for sid, row in rows.items() if row["priority"] != "none"}
    return {
        "evaluation_version": VERSION,
        "normalization": NORMALIZATION,
        "report_sha256": bound,
        "analysis_id": report["analysis_id"],
        "transcript_version": report["transcript_version"],
        "review_policy_version": report["policy_version"],
        "total_segments": len(rows),
        "recognition_flagged": len(recognition),
        "review_queue_flagged": len(queue),
        "display_flagged": sum(
            bool(
                set(row["display_reasons"])
                - {"WORD_TIMESTAMPS_UNAVAILABLE", "UNALIGNED_WORD_TIMESTAMPS"}
            )
            for row in rows.values()
        ),
        "quality_available": sum(bool(row["quality"]) for row in rows.values()),
        "human_labeled_segments": len(labels),
        "reference_segments": len(corrections),
        "reference_coverage": ratio(len(corrections), len(rows)),
        "reference_characters": characters,
        "character_edits": distances,
        "cer": ratio(distances, characters),
        "cer_scope": "full_transcript"
        if rows and len(corrections) == len(rows)
        else "verified_subset"
        if corrections
        else "unavailable_no_verified_reference",
        "recognition_detector": detector(recognition),
        "review_queue": detector(queue),
        "per_segment": per_segment,
        "review_time_seconds": None,
        "quality_pass": None,
        "external_calls": 0,
    }
