"""Generate a private offline evaluation and a listening/reference-entry pack."""

import argparse
import html
import json
import shutil
from pathlib import Path

from app.domain.transcript_evaluation import compare_runs, evaluate, reference_template


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--references", type=Path)
    parser.add_argument(
        "--comparison-transcript", type=Path, help="Stability comparison, not truth"
    )
    parser.add_argument("--audio", type=Path, help="Existing MP3; copied without conversion")
    parser.add_argument("--output", type=Path, required=True, help="New private directory")
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    references = (
        json.loads(args.references.read_text(encoding="utf-8")) if args.references else None
    )
    result = evaluate(report, references)
    if args.comparison_transcript:
        result["run_agreement"] = compare_runs(
            report, json.loads(args.comparison_transcript.read_text(encoding="utf-8"))
        )
    refs = references if references is not None else reference_template(report)
    if args.audio and (args.audio.suffix.lower() != ".mp3" or not args.audio.is_file()):
        parser.error("--audio must point to an existing MP3")
    # No overwrite, including the source transcript/reference/audio files.
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in (("evaluation.json", result), ("references.json", refs)):
        (args.output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.audio:
        shutil.copyfile(args.audio, args.output / "audio.mp3")
    data = json.dumps({"report": report, "references": refs}, ensure_ascii=False).replace(
        "<", "\\u003c"
    )
    (args.output / "review.html").write_text(
        Path(__file__).with_suffix(".html").read_text(encoding="utf-8").replace("__DATA__", data),
        encoding="utf-8",
    )
    cer = "평가 불가: 확인된 정답 전사 없음" if result["cer"] is None else str(result["cer"])
    (args.output / "report.md").write_text(
        "# 전사 품질 평가\n\n"
        f"- 전체 구간: {result['total_segments']}\n"
        f"- 검수 대기 표시: {result['review_queue_flagged']}\n"
        f"- 인식 의심 신호: {result['recognition_flagged']}\n"
        f"- 사람이 확인한 인식 판정: {result['human_labeled_segments']}\n"
        f"- 정답 전사 구간: {result['reference_segments']}\n"
        f"- 글자 오류율(CER): {html.escape(cer)}\n\n"
        "검사 성공은 인식 품질 통과가 아닙니다. "
        "부분 표본의 결과를 전체 정확도로 해석하지 않습니다.\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "cer": result["cer"], "external_calls": 0}))


if __name__ == "__main__":
    main()
