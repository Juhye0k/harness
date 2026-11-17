"""Host-only fault harness. Its generated Compose project is the sole mutation target."""

import argparse
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def validate_project(project):
    if not re.fullmatch(r"shortform-failure-[a-f0-9]{12}", project):
        raise ValueError("Only an internally generated failure project may be controlled")


class Drill:
    def __init__(self, source, image, directory):
        self.project = "shortform-failure-" + uuid4().hex[:12]
        validate_project(self.project)
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=False)
        mounts = [
            {
                "type": "bind",
                "source": str(source / name),
                "target": f"/app/{name}",
                "read_only": True,
            }
            for name in [
                "app",
                "tests",
                "scripts",
                "migrations",
                "AGENTS.md",
                "pyproject.toml",
                "uv.lock",
                "alembic.ini",
                "compose.integration.yaml",
            ]
        ]
        override = {
            "services": {
                name: {"image": image, "volumes": mounts}
                for name in ["api", "migrate", "worker", "analysis-worker", "sns-worker", "runner"]
            }
        }
        path = directory / "private-override.json"
        path.write_text(json.dumps(override), encoding="utf-8")
        self.command = [
            "docker",
            "compose",
            "-p",
            self.project,
            "-f",
            str(source / "compose.integration.yaml"),
            "-f",
            str(path),
        ]
        config = json.loads(self.run("config", "--format", "json"))
        for volume in config.get("volumes", {}).values():
            if volume.get("external") or not volume["name"].startswith(self.project + "_"):
                raise ValueError("Unowned volume")
        for service in config["services"].values():
            if service.get("ports"):
                raise ValueError("Drills may not publish host ports")
            for mount in service.get("volumes", []):
                if mount["type"] == "bind" and (
                    not mount.get("read_only")
                    or Path(mount["source"]).resolve()
                    not in {
                        (source / name).resolve()
                        for name in [
                            "app",
                            "tests",
                            "scripts",
                            "migrations",
                            "AGENTS.md",
                            "pyproject.toml",
                            "uv.lock",
                            "alembic.ini",
                            "compose.integration.yaml",
                        ]
                    }
                ):
                    raise ValueError("Unexpected bind mount")
        for name in ["api", "runner", "worker", "analysis-worker", "sns-worker"]:
            env = config["services"][name]["environment"]
            if (
                env["APP_ENV"] != "test"
                or env["ENABLE_PAID_AI"] != "false"
                or env["YOUTUBE_CLIENT_ID"] != "fake-integration-client"
            ):
                raise ValueError("Only fixture providers allowed")
            if any(env.get(key) for key in ["GROQ_API_KEY", "OPENAI_API_KEY", "AZURE_SPEECH_KEY"]):
                raise ValueError("Real keys forbidden")

    def run(self, *args, timeout=100):
        validate_project(self.project)
        result = subprocess.run(
            self.command + list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode:
            raise RuntimeError(f"Compose {args[0]} failed: " + result.stderr[-2000:])
        return result.stdout

    def client(self, action, identifier=None):
        args = [
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "runner",
            "/app/.venv/bin/python",
            "-m",
            "tests.integration.drill_client",
            action,
        ]
        if identifier:
            args += ["--id", str(identifier)]
        return json.loads(self.run(*args).strip().splitlines()[-1])

    def up(self, *services):
        self.run("up", "--no-build", "-d", *services)
        if "api" not in services:
            return
        deadline = time.monotonic() + 90
        cid = self.run("ps", "-q", "api").strip()
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["docker", "inspect", cid, "--format", "{{.State.Health.Status}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip() == "healthy":
                return
            time.sleep(0.2)
        raise TimeoutError("Isolated API never became healthy")

    def kill(self, service):
        if service not in {"api", "worker", "analysis-worker", "sns-worker"}:
            raise ValueError("Unexpected target")
        cid = self.run("ps", "-q", service).strip()
        assert cid
        self.run("kill", "-s", "SIGKILL", service)
        result = subprocess.run(
            ["docker", "inspect", cid, "--format", "{{json .State}}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        state = json.loads(result.stdout)
        assert not state["Running"] and state["Pid"] == 0

    def mark(self, service, *arguments):
        self.run("run", "--rm", "--no-deps", "-T", service, "/app/.venv/bin/python", *arguments)

    def execute(self):
        report = {
            "project": self.project,
            "providers": "fixtures",
            "scenarios": {},
            "cleanup": False,
        }
        try:
            self.up("api", "worker", "analysis-worker", "sns-worker")
            video = self.client("prepare-video")["job_id"]
            self.client("video-paused", video)
            self.kill("worker")
            self.run("stop", "-t", "2", "api")
            self.mark(
                "worker",
                "-m",
                "app.cli.fail_job",
                video,
                "--confirmed-stopped",
                "--reason",
                "isolated worker termination verified",
            )
            self.up("api", "worker")
            report["scenarios"]["video_worker_killed"] = self.client("verify-video", video)

            request_id = uuid4()
            self.client("arm-request", request_id)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.client, "submit-analysis", request_id)
                analysis = self.client("analysis-paused", request_id)["analysis_id"]
                self.kill("api")
                self.run("stop", "-t", "2", "analysis-worker")
                assert future.result(timeout=35)["response_lost"]
            self.mark(
                "analysis-worker",
                "-m",
                "app.cli.fail_job",
                analysis,
                "--analysis",
                "--confirmed-stopped",
                "--reason",
                "isolated API and analysis worker termination verified",
            )
            self.up("api", "analysis-worker")
            report["scenarios"]["api_killed_after_publish"] = self.client(
                "verify-analysis", analysis
            )

            upload = self.client("prepare-sns")["upload_id"]
            self.client("sns-paused", upload)
            self.kill("sns-worker")
            self.run("stop", "-t", "2", "api")
            self.mark("sns-worker", "-m", "app.cli.mark_upload_unknown", upload, "--worker-stopped")
            self.up("api", "sns-worker")
            report["scenarios"]["sns_worker_killed_after_send"] = self.client("verify-sns", upload)
            report["passed"] = True
        except BaseException as exc:
            report["passed"] = False
            report["error_type"] = type(exc).__name__
            raise
        finally:
            try:
                (self.directory / "private-logs.txt").write_text(
                    self.run("logs", "--no-color", "--tail", "80"), encoding="utf-8"
                )
            except Exception:
                report["logs_available"] = False
            try:
                self.run("down", "--volumes", "--remove-orphans")
                report["cleanup"] = True
            finally:
                (self.directory / "result.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8"
                )
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--image", default="shortform-harness:integration")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / ".artifacts/failure-drills")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_relative_to(ROOT):
        parser.error("Source must stay inside this workspace")
    directory = args.artifact_dir.resolve() / uuid4().hex
    if not directory.is_relative_to(ROOT):
        parser.error("Artifacts must stay inside this workspace")
    report = Drill(source, args.image, directory).execute()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
