"""Regression guard for F-CI-008 hardened production-image smoke test."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict[str, Any]:
    assert CI_WORKFLOW.is_file(), f"missing {CI_WORKFLOW}"
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def _image_smoke_command() -> str:
    steps = _workflow()["jobs"]["image-build"]["steps"]
    docker_steps = [step for step in steps if "docker run" in step.get("run", "")]
    assert len(docker_steps) == 1, "image-build job must have exactly one docker run smoke step"
    return docker_steps[0]["run"]


def _has_flag(command: str, flag: str, value: str | None = None) -> bool:
    if value is None:
        return re.search(rf"(^|\s){re.escape(flag)}(\s|\\\n|$)", command) is not None
    return re.search(rf"(^|\s){re.escape(flag)}[=\s]{re.escape(value)}(\s|\\\n|$)", command) is not None


def test_image_smoke_container_runs_without_network_or_host_ports() -> None:
    command = _image_smoke_command()

    assert _has_flag(command, "--network", "none"), (
        "F-CI-008: production image smoke test must run with --network=none"
        " so a poisoned image cannot call out from the GitHub runner."
    )
    assert "-p 8000:8000" not in command
    assert "--publish" not in command
    assert "curl -sf http://localhost:8000/ready" not in command


def test_image_smoke_container_drops_runtime_privileges() -> None:
    command = _image_smoke_command()

    assert _has_flag(command, "--read-only"), "F-CI-008: smoke container must use --read-only."
    assert _has_flag(command, "--cap-drop", "ALL"), "F-CI-008: smoke container must drop all Linux capabilities."
    assert _has_flag(command, "--security-opt", "no-new-privileges"), (
        "F-CI-008: smoke container must set --security-opt no-new-privileges."
    )
    assert _has_flag(command, "--user", "65534:65534") or _has_flag(command, "--user", "65534"), (
        "F-CI-008: smoke container must force a non-root runtime user."
    )


def test_image_smoke_keeps_a_meaningful_in_container_check() -> None:
    command = _image_smoke_command()

    assert "dataforge:ci-test" in command
    assert "python" in command
    assert "app.main" in command, (
        "F-CI-008: replacing the HTTP smoke with --network=none still needs an in-container app import/startup check."
    )
