"""Fixed-input local comparison loop. Does not write revisions, approve, render, or publish."""

import argparse
import hashlib
import html
import json
from pathlib import Path
from string import Template

from app.domain.source_caption_evaluation import compare, screen_transitions
from app.domain.source_caption_proposal import propose, youtube_onsets


def verified_track(raw_bytes, provenance, editor, duration_ms):
    if (
        provenance.get("source_sha256") != editor.get("source_sha256")
        or provenance.get("caption_sha256") != hashlib.sha256(raw_bytes).hexdigest()
        or not editor.get("source_video_id")
        or provenance.get("source_video_id") != editor["source_video_id"]
        or provenance.get("acquired_video_id") != editor["source_video_id"]
        or provenance.get("duration_ms") != duration_ms
    ):
        raise ValueError("Caption acquisition provenance does not match original or track")
    return json.loads(raw_bytes)


def render(report, video_url=None):
    details = report.get("proposal_details", {})
    cut = "".join(
        f"<li>{html.escape(row['text'])}: {row['start_ms'] / 1000:.2f}초 시작, "
        f"다음 단어 {row['next_onset_ms'] / 1000:.2f}초</li>"
        for row in details.get("cut_words", [])
    )
    proposed = report["proposed_cues"]
    suggested_range = (
        f"{proposed[0]['start_ms'] / 1000:.2f}–{proposed[-1]['end_ms'] / 1000:.2f}초"
        if proposed
        else "제안 없음"
    )
    rows = []
    for name, label in (("baseline", "기존 편집본"), ("screen_draft", "비교 초안")):
        row = report[name]
        cer = row["screen_reference_cer"]
        interval = row["interval_screen_reference_cer"]
        rows.append(
            f"<tr><td>{label}</td><td>{'미평가' if cer is None else f'{cer:.1%}'}</td>"
            f"<td>{'미평가' if interval is None else f'{interval:.1%}'}</td>"
            f"<td>{row['character_edits']} / {row['reference_characters']}</td>"
            f"<td>{html.escape(json.dumps(row['policy_violations'], ensure_ascii=False))}</td></tr>"
        )
    captions = "".join(
        f"<tr><td>{c['start_ms'] / 1000:.2f}–{c['end_ms'] / 1000:.2f}초</td>"
        f"<td>{html.escape(c['text'])}</td>"
        f"<td>{html.escape(str(c.get('samples', '미제공')))}</td></tr>"
        for c in report["reference_cues"]
    )
    blocked = "".join(
        f"<tr><td>{c['start_ms'] / 1000:.2f}–{c['end_ms'] / 1000:.2f}초</td>"
        f"<td>{html.escape(c['reason'])}</td></tr>"
        for c in report["reference"]["blocked"]
    )
    proposals = []
    for c in proposed:
        stamp = f"{c['start_ms'] / 1000:.2f}초"
        if video_url:
            stamp = (
                f'<button type="button" data-seek="{c["start_ms"] / 1000}">{stamp} 재생</button>'
            )
        proposals.append(
            f"<tr><td>{stamp}</td><td>{(c['end_ms'] - c['start_ms']) / 1000:.2f}초</td>"
            f"<td>{html.escape(' / '.join(c.get('lines', [c.get('text', '')])))}</td></tr>"
        )
    video = (
        f'<video controls preload="metadata" src="{html.escape(video_url, quote=True)}"></video>'
        if video_url
        else ""
    )
    return Template(Path(__file__).with_suffix(".html").read_text(encoding="utf-8")).substitute(
        rows="".join(rows),
        captions=captions,
        blocked=blocked,
        video=video,
        coverage_seconds=f"{report['reference']['reference_coverage_ms'] / 1000:.2f}",
        coverage_ratio=f"{report['reference']['reference_coverage_ratio']:.1%}",
        revision_id=html.escape(report["revision_id"]),
        decision=html.escape(report["decision"]["action"]),
        proposal_origin=html.escape(report.get("proposal_origin", "even_frame_ocr")),
        cue_count=len(proposed),
        suggested_range=suggested_range,
        cut_words=cut,
        proposals="".join(proposals),
        range_label="단어 시작 시각 기준 제안 범위" if details else "OCR 초안 표시 범위",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr", type=Path, required=True)
    parser.add_argument("--editor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--video-url")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--youtube-captions", type=Path)
    parser.add_argument("--caption-provenance", type=Path)
    parser.add_argument("--duration-ms", type=int)
    parser.add_argument(
        "--align-to-ocr",
        action="store_true",
        help="Prefer caption breaks near persistent OCR transitions in even frames",
    )
    args = parser.parse_args()
    if args.align_to_ocr and not args.youtube_captions:
        parser.error("--align-to-ocr requires --youtube-captions")
    inputs = {
        name: path.read_bytes() for name, path in (("ocr", args.ocr), ("editor", args.editor))
    }
    fixed = None
    if args.reference:
        inputs["reference"] = args.reference.read_bytes()
        fixed = json.loads(inputs["reference"])
    editor = json.loads(inputs["editor"])
    observation = json.loads(inputs["ocr"])
    proposal = None
    if args.youtube_captions:
        if not args.caption_provenance:
            parser.error("--caption-provenance is required with --youtube-captions")
        inputs["youtube_captions"] = args.youtube_captions.read_bytes()
        inputs["caption_provenance"] = args.caption_provenance.read_bytes()
        track = verified_track(
            inputs["youtube_captions"],
            json.loads(inputs["caption_provenance"]),
            editor,
            args.duration_ms,
        )
        words = youtube_onsets(track, args.duration_ms)
        snap_ms, changes = (
            screen_transitions(observation, editor["start_ms"], editor["end_ms"])
            if args.align_to_ocr
            else (0, [])
        )
        proposal = propose(
            words,
            editor["segments"],
            editor["start_ms"],
            editor["end_ms"],
            screen_changes=changes,
            snap_ms=snap_ms,
        )
        if not proposal["cues"]:
            raise ValueError("No complete readable source caption proposal")
    report = compare(observation, editor, fixed, proposal["cues"] if proposal else None)
    if proposal:
        report["proposal_origin"] = (
            "youtube_automatic_captions_with_even_frame_ocr_transitions"
            if args.align_to_ocr
            else "youtube_automatic_captions_not_author_subtitles"
        )
        report["proposal_details"] = {k: v for k, v in proposal.items() if k != "cues"}
        if args.align_to_ocr:
            report["proposal_details"]["screen_alignment"] = {
                "version": "persistent-ocr-breaks-v1",
                "input_fold": 0,
                "snap_tolerance_ms": snap_ms,
                "observed_transitions_ms": changes,
            }
    report["input_sha256"] = {
        name: hashlib.sha256(data).hexdigest() for name, data in inputs.items()
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "report.html").write_text(render(report, args.video_url), encoding="utf-8")
    if not all(
        path.read_bytes() == inputs[name]
        for name, path in (("ocr", args.ocr), ("editor", args.editor))
    ):
        raise ValueError("Frozen evaluation inputs changed during comparison")
    print(
        json.dumps(
            {
                "reference_coverage": report["reference"]["reference_coverage_ratio"],
                "baseline_screen_cer": report["baseline"]["screen_reference_cer"],
                "draft_screen_cer": report["screen_draft"]["screen_reference_cer"],
                "baseline_interval_cer": report["baseline"]["interval_screen_reference_cer"],
                "draft_interval_cer": report["screen_draft"]["interval_screen_reference_cer"],
                "draft_policy_violations": report["screen_draft"]["policy_violations"],
                "production_ready": False,
                "external_calls": 0,
                "decision": report["decision"],
            }
        )
    )


if __name__ == "__main__":
    main()
