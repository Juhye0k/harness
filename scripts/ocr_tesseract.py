"""Offline OCR over existing crops; never sends frames to an external provider."""

import argparse
import csv
import io
import json
import subprocess
from pathlib import Path


def parse_words(tsv):
    # TSV OCR text can itself contain quotes; CSV quoting would swallow later rows.
    return [
        {"text": word["text"], "confidence": float(word["conf"])}
        for word in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
        if word["text"].strip() and float(word["conf"]) >= 0
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language", choices=("kor", "kor+eng"), default="kor")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve previous runs")
    data = json.loads(args.input.read_text(encoding="utf-8"))
    output = []
    for index, row in enumerate(data["frames"], 1):
        path = args.frames / f"frame-{index:04d}.{args.input.stem}.png"
        words = []
        if row["region"] is not None:
            result = subprocess.run(
                [
                    "tesseract",
                    str(path),
                    "stdout",
                    "-l",
                    args.language,
                    "--psm",
                    "7",
                    "--dpi",
                    "300",
                    "tsv",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=True,
            )
            words = parse_words(result.stdout)
        output.append(
            {
                **row,
                "text": " ".join(word["text"] for word in words),
                "confidence": (
                    sum(word["confidence"] for word in words) / len(words) if words else None
                ),
                "ocr_words": words,
            }
        )
    data.update(engine="tesseract", frames=output, external_calls=0, human_verified=False)
    data["engine_version"] = subprocess.run(
        ["tesseract", "--version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()[0]
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"frames": len(output), "nonempty": sum(bool(r["text"]) for r in output)}))


if __name__ == "__main__":
    main()
