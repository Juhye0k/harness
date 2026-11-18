"""Extract a bounded caption band; preserve the original and every prior run."""

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--fps", type=int, choices=(5, 10, 20), default=10)
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"), required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    x, y, width, height = args.roi
    if (
        not args.source.is_file()
        or not all(math.isfinite(t) for t in (args.start, args.end))
        or not 0 <= args.start < args.end
        or args.end - args.start > 60
        or min(x, y) < 0
        or min(width, height) < 1
        or max(width, height) > 4096
    ):
        parser.error("Valid local file, <=60 seconds, and a bounded positive ROI are required")
    before = sha256(args.source)
    args.output.mkdir(parents=True, exist_ok=False)
    frames_dir = args.output / "frames"
    frames_dir.mkdir()
    subprocess.run(
        [
            args.ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-n",
            "-ss",
            str(args.start),
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(args.source.resolve()),
            "-t",
            str(args.end - args.start),
            "-vf",
            f"fps={args.fps},crop={width}:{height}:{x}:{y}:exact=1",
            str(frames_dir / "frame-%04d.png"),
        ],
        timeout=60,
        check=True,
    )
    if sha256(args.source) != before:
        raise ValueError("Source changed while extracting frames")
    start_ms = round(args.start * 1000)
    step_ms = 1000 // args.fps
    frames = [
        {
            "path": str(path.resolve()),
            "time_ms": start_ms + index * step_ms,
            "sha256": sha256(path),
        }
        for index, path in enumerate(sorted(frames_dir.glob("frame-*.png")))
    ]
    if not frames:
        raise ValueError("No frames in selected source range")
    manifest = {
        "source_sha256": before,
        "sample_step_ms": 1000 // args.fps,
        "roi": args.roi,
        "frames": frames,
        "sampling_uncertainty_ms": 1000 // args.fps,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    print(json.dumps({"frames": len(frames), "source_preserved": True}))


if __name__ == "__main__":
    main()
