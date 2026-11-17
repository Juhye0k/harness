import json
import sys

import pytest

from scripts import recommendation_loop as loop
from scripts.evaluate_recommendations import save_new


def session(tmp_path, monkeypatch, worker=True):
    monkeypatch.setattr(loop, "ROOT", tmp_path)
    (tmp_path / "app").mkdir()
    value = tmp_path / "app/value.py"
    value.write_text("0")
    for name in ("pyproject.toml", "uv.lock", "compose.integration.yaml"):
        (tmp_path / name).write_text("fixture")
    script = tmp_path / "fixture.py"
    script.write_text(
        "import sys,json\nfrom pathlib import Path\n"
        f"p=Path({str(value)!r})\n"
        "if sys.argv[1]=='fix':\n"
        " task=json.load(sys.stdin); p.write_text(str(int(p.read_text())+1))\n"
        "else: sys.exit(0 if int(p.read_text())>=4 else 1)\n",
        encoding="utf-8",
    )
    command = [sys.executable, str(script)]
    policy = loop.Policy(
        checks={"basic": command + ["check"], "integration": command + ["check"]},
        worker=command + ["fix"] if worker else [],
        issues=[],
    ).model_dump()
    directory = tmp_path / "session"
    save_new(
        directory / "session.json",
        {"policy": policy, "protected_files": {}, "initial_source_sha256": loop.code_hash()},
    )
    return directory, value


def test_actual_loop_repairs_more_than_three_times_and_runs_two_full_passes(tmp_path, monkeypatch):
    directory, value = session(tmp_path, monkeypatch)
    assert loop.main(["run", str(directory), "--seconds", "30"]) == 0
    assert value.read_text() == "4"
    _, events = loop.load(directory)
    assert len([e for e in events if e["kind"] == "worker"]) == 4
    assert events[-1]["passed"] and events[-2]["passed"]


def test_no_worker_does_not_fake_completion(tmp_path, monkeypatch):
    directory, _ = session(tmp_path, monkeypatch, worker=False)
    assert loop.main(["run", str(directory), "--seconds", "10"]) == 2


def test_protected_acceptance_change_is_rejected(tmp_path, monkeypatch):
    directory, value = session(tmp_path, monkeypatch)
    data = loop.read(directory / "session.json")
    import hashlib

    data["protected_files"] = {"app/value.py": hashlib.sha256(value.read_bytes()).hexdigest()}
    (directory / "session.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Protected"):
        loop.main(["run", str(directory), "--seconds", "15"])


def test_time_budget_and_missing_human_review_are_not_success(tmp_path, monkeypatch):
    directory, value = session(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        loop.main(["run", str(directory), "--seconds", "0"])
    data = loop.read(directory / "session.json")
    data["policy"]["issues"] = [
        {
            "id": "quality",
            "severity": "major",
            "description": "needs listening",
            "evidence": "private review",
            "verification": "human",
        }
    ]
    (directory / "session.json").write_text(json.dumps(data))
    value.write_text("4")
    assert loop.main(["run", str(directory), "--seconds", "10"]) == 2
    assert not any(e["kind"] == "worker" for e in loop.load(directory)[1])


def test_timeout_and_session_lock_are_explicit(tmp_path, monkeypatch):
    result = loop.execute([sys.executable, "-c", "import time; time.sleep(10)"], 0.1)
    assert result == {"passed": False, "error": "TIMEOUT"}
    directory, _ = session(tmp_path, monkeypatch)
    (directory / "execution.lock").write_text("other execution")
    with pytest.raises(FileExistsError):
        loop.main(["run", str(directory), "--seconds", "1"])


def test_event_tampering_is_rejected(tmp_path, monkeypatch):
    directory, _ = session(tmp_path, monkeypatch, worker=False)
    loop.main(["check", str(directory), "--seconds", "5"])
    event_path = directory / "event-000000.json"
    event = loop.read(event_path)
    event["previous_sha256"] = "wrong"
    event_path.write_text(json.dumps(event))
    with pytest.raises(ValueError, match="Broken"):
        loop.load(directory)
