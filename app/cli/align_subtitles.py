"""Offline saved-response alignment. No model call or source/DB modification."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from app.domain.subtitles import build_subtitles, compact, srt
from app.domain.word_alignment import recover


def measure(subtitles):
    cues = subtitles["cues"]
    constraints = {
        "TEXT_LIMIT",
        "DURATION_LIMIT",
        "SHORT_DURATION",
        "READING_SPEED",
        "OVERLAPPING_CUES",
    }
    return {
        "cues": len(cues),
        "constraint_flagged_cues": sum(bool(set(c["warnings"]) & constraints) for c in cues),
        "max_lines": max((len(c["lines"]) for c in cues), default=0),
        "max_duration_ms": max((c["end_ms"] - c["start_ms"] for c in cues), default=0),
        "long_cues": sum("DURATION_LIMIT" in c["warnings"] for c in cues),
        "text_limit_cues": sum("TEXT_LIMIT" in c["warnings"] for c in cues),
    }


def compare(transcript, raw, duration_ms, tolerance_ms=0):
    segments = transcript["segments"]
    before = deepcopy(segments)
    if len(segments) != len(raw["segments"]):
        raise ValueError("Source segment count differs from saved response")
    for source, provider in zip(segments, raw["segments"], strict=True):
        if (
            source["text"] != provider["text"].strip()
            or source["start_ms"] != round(provider["start"] * 1000)
            or source["end_ms"] != round(provider["end"] * 1000)
            or source["end_ms"] > duration_ms
        ):
            raise ValueError("Saved response does not belong to the source transcript")
    recovered, report = recover(
        segments, raw.get("words"), boundary_tolerance_ms=tolerance_ms, duration_ms=duration_ms
    )
    display = deepcopy(recovered)
    deltas = []
    for source, row in zip(segments, display, strict=True):
        if "words" in row:
            start, end = row["words"][0]["start_ms"], row["words"][-1]["end_ms"]
            deltas.append(
                {
                    "segment_id": row["id"],
                    "start_delta_ms": start - source["start_ms"],
                    "end_delta_ms": end - source["end_ms"],
                }
            )
            if tolerance_ms:
                row["start_ms"], row["end_ms"] = (
                    min(row["start_ms"], start),
                    max(row["end_ms"], end),
                )
    subtitles = build_subtitles(display)
    if tolerance_ms:
        subtitles.update(
            version="ko-display-bounded-preview-v1", policy_status="experimental_boundary_preview"
        )
    assert segments == before
    for segment in segments:
        emitted = [c for c in subtitles["cues"] if c["source_segment_id"] == segment["id"]]
        if compact("".join(c["text"] for c in emitted)) != compact(segment["text"]):
            raise ValueError("Source text was lost or duplicated")
    report.update(
        {
            "before": measure(build_subtitles(segments)),
            "after": measure(subtitles),
            "boundary_deltas": deltas,
            "source_preserved": True,
            "external_calls": 0,
            "acoustic_accuracy_verified": False,
        }
    )
    return subtitles, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--duration-ms", type=int, required=True)
    parser.add_argument("--boundary-tolerance-ms", type=int, choices=(0, 150, 250), default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 0 < args.duration_ms <= 1_200_000:
        parser.error("Duration must be within 20 minutes")
    transcript_bytes, response_bytes = args.transcript.read_bytes(), args.response.read_bytes()
    subtitles, report = compare(
        json.loads(transcript_bytes),
        json.loads(response_bytes),
        args.duration_ms,
        args.boundary_tolerance_ms,
    )
    report.update(
        transcript_sha256=hashlib.sha256(transcript_bytes).hexdigest(),
        response_sha256=hashlib.sha256(response_bytes).hexdigest(),
    )
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in (("subtitles.json", subtitles), ("alignment-report.json", report)):
        (args.output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (args.output / "subtitles.srt").write_text(srt(subtitles), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "matched": report["matched_segments"],
                "before": report["before"],
                "after": report["after"],
            }
        )
    )


if __name__ == "__main__":
    main()
