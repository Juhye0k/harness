"""Explicitly copy approved comparison assets; never mount an entire artifact tree."""

import argparse
import json
import shutil
from pathlib import Path
from uuid import UUID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-id", type=UUID, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    allowed = ["before.png", "after.png", "remaining-long.png", "preview-after.mp4"]
    files = [name for name in allowed if (source / name).is_file()]
    if not files:
        parser.error("No supported evaluation assets")
    for name in files:
        if not (source / name).resolve().is_relative_to(source):
            parser.error("Asset escapes source directory")
    target = args.data_dir.resolve() / "verification" / str(args.analysis_id)
    target.mkdir(parents=True, exist_ok=False)
    for name in files:
        shutil.copyfile(source / name, target / name)
    (target / "manifest.json").write_text(
        json.dumps({name: name for name in files}), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
