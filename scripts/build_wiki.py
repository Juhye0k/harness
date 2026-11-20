"""Compile reviewed Wiki sources without publishing or deleting remote pages."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "wiki"
BASE = "https://github.com/Juhye0k/short-form"
LINK = re.compile(r"(!?\[[^\]]*\]\()([^\s)]+)(\))")


def slug(path):
    if path.relative_to(WIKI).as_posix() == "05-development/harness-workflow.md":
        return "05-development-harness-workflow-legacy"
    parts = list(path.relative_to(WIKI).with_suffix("").parts)
    if parts[-1] == "README":
        parts.pop()
    return "-".join(parts) or "Home"


def compile_wiki(output):
    navigation = json.loads((WIKI / "navigation.json").read_text(encoding="utf-8"))
    paths = [WIKI / item["path"] for item in navigation["pages"]]
    archived = [WIKI / name for name in navigation["repository_only"]]
    classified = paths + archived
    actual = set(WIKI.rglob("*.md"))
    assert len(classified) == len(set(classified)) and set(classified) == actual, (
        "Each Wiki source must be public or repository-only exactly once"
    )
    public = set(paths)
    assert len({slug(path) for path in paths}) == len(paths), "Duplicate Wiki URL"
    assert all(item["category"] in navigation["categories"] for item in navigation["pages"])
    output.mkdir(parents=True, exist_ok=True)
    expected = {slug(path) + ".md" for path in paths} | {"_Sidebar.md"}
    stale = {path.name for path in output.glob("*.md")} - expected
    if stale:
        raise ValueError(f"Use a fresh preview directory. Obsolete pages present: {sorted(stale)}")
    sidebar = ["# Shortform", "", f"[처음 읽기]({BASE}/wiki)", ""]
    links = 0
    for category in navigation["categories"]:
        sidebar += ["<details>", f"<summary>{category}</summary>", ""]
        for item in navigation["pages"]:
            path = WIKI / item["path"]
            if item["category"] != category or path == WIKI / "README.md":
                continue
            title = path.read_text(encoding="utf-8").splitlines()[0][2:]
            title = title.split(" — ")[0]
            sidebar.append(f"- [{title}]({BASE}/wiki/{slug(path)})")
        sidebar += ["", "</details>", ""]
    (output / "_Sidebar.md").write_text("\n".join(sidebar), encoding="utf-8")
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert source.splitlines()[2].startswith("> "), f"Missing opening summary: {path}"

        def convert(match, source_path=path):
            nonlocal links
            target = match[2]
            if ":" in target or target.startswith(("#", "/")):
                return match[0]
            name, separator, anchor = target.partition("#")
            resolved = (source_path.parent / unquote(name)).resolve()
            assert resolved.is_relative_to(ROOT), f"Escaped repository: {target}"
            assert resolved.exists(), f"Missing link: {source_path}: {target}"
            links += 1
            if resolved in public:
                url = BASE + "/wiki/" + slug(resolved)
            elif match[1].startswith("!"):
                url = BASE.replace("github.com", "raw.githubusercontent.com") + "/main/"
                url += resolved.relative_to(ROOT).as_posix()
            elif resolved.is_dir():
                url = BASE + "/tree/main/" + resolved.relative_to(ROOT).as_posix()
            else:
                url = BASE + "/blob/main/" + resolved.relative_to(ROOT).as_posix()
            if separator:
                url += "#" + anchor
            return match[1] + url + match[3]

        rendered = LINK.sub(convert, source)
        (output / (slug(path) + ".md")).write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "pages": len(paths),
                "categories": len(navigation["categories"]),
                "relative_links": links,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT / ".tmp"):
        parser.error("Output must stay in the workspace .tmp directory")
    compile_wiki(destination)
