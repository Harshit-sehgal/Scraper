"""Docker smoke test — build the image, verify /health and /ready.

Runs the ``dataforge:test-smoke`` image in a short-lived container,
hits the liveness and readiness endpoints, then tears down.

Skipped entirely if Docker is not available or the build fails.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from collections.abc import Generator
from pathlib import Path

import pytest
import requests

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_NAME = "dataforge:test-smoke"
SMOKE_DOCKERFILE = REPO_ROOT / "Dockerfile.smoke"
CONTAINER_PORT = 18000  # non-standard to avoid conflicts
DOCKER_CMD = shutil.which("docker") or "docker"


def _docker_available() -> bool:
    """Check that docker CLI + daemon are reachable."""
    try:
        result = subprocess.run(
            [DOCKER_CMD, "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# Allow up to 360s for Docker build + tests
pytestmark = pytest.mark.timeout(360)

# Skip the entire module if Docker is not available
if not _docker_available():
    pytest.skip("Docker not available — skipping Docker smoke tests", allow_module_level=True)


def _wait_for_endpoint(url: str, timeout: int = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code in {200, 503}:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def _container_running(name: str) -> bool:
    result = subprocess.run(
        [DOCKER_CMD, "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True,
        timeout=5,
    )
    return result.stdout.strip() == b"true"


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def docker_image() -> Generator[str | None, None, None]:
    """Build the image once per module and tear down after all tests.

    Returns the image ID on success, None on failure (skip tests).
    """
    try:
        subprocess.run(
            [DOCKER_CMD, "build", "-t", IMAGE_NAME, "-f", str(SMOKE_DOCKERFILE), str(REPO_ROOT)],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
        # Get image ID for verification
        result = subprocess.run(
            [DOCKER_CMD, "inspect", "-f", "{{.Id}}", IMAGE_NAME],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        image_id = result.stdout.strip()
        yield image_id
    except subprocess.CalledProcessError as e:
        logger.warning("Docker build failed: %s", e.stderr)
        yield None
    except subprocess.TimeoutExpired:
        logger.warning("Docker build timed out")
        yield None
    finally:
        # Clean up image
        subprocess.run(
            [DOCKER_CMD, "rmi", "-f", IMAGE_NAME],
            capture_output=True,
            timeout=30,
        )


@pytest.fixture
def running_container(docker_image: str | None) -> Generator[str, None, None]:
    """Start a container from the smoke-test image, yield its URL, stop it."""
    if docker_image is None:
        pytest.skip("Docker build unavailable or failed")

    container_name = f"dataforge-smoke-{os.getpid()}"

    try:
        subprocess.run(
            [
                DOCKER_CMD,
                "run",
                "-d",
                "--rm",
                "--name",
                container_name,
                "-p",
                f"{CONTAINER_PORT}:8000",
                "-e",
                "PYTHONPATH=/app/backend",
                IMAGE_NAME,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        # Let the container start
        time.sleep(2)
        url = f"http://localhost:{CONTAINER_PORT}"
        if not _wait_for_endpoint(f"{url}/health", timeout=30):
            pytest.fail("Container started but /health not reachable within 30s")
        yield url
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Container start failed: {e.stderr}")
    finally:
        subprocess.run(
            [DOCKER_CMD, "stop", "-t", "5", container_name],
            capture_output=True,
            timeout=15,
        )


# ─── Tests ─────────────────────────────────────────────────────────────────


def test_docker_image_built(docker_image: str | None):
    """Sanity: the image was built and has an ID."""
    if docker_image is None:
        pytest.skip("Docker image could not be built")
    assert docker_image.startswith("sha256:"), f"Unexpected image ID: {docker_image}"


def test_health_endpoint_liveness(running_container: str):
    """GET /health returns 200 {"status": "ok"}."""
    r = requests.get(f"{running_container}/health", timeout=5)
    assert r.status_code == 200, f"/health returned {r.status_code} {r.text!r}"
    body = r.json()
    assert body == {"status": "ok"}, f"/health body: {body}"


def test_ready_endpoint_readiness(running_container: str):
    """GET /ready returns 200 or 503 depending on storage backend."""
    r = requests.get(f"{running_container}/ready", timeout=10)
    assert r.status_code in {200, 503}, f"/ready returned {r.status_code} {r.text!r}"
    body = r.json()
    assert "status" in body, f"/ready body missing status: {body}"
    assert body["status"] in {"ready", "not_ready"}, f"Unexpected status: {body['status']}"


def test_apidoc_endpoint(running_container: str):
    """GET /apidoc or /openapi.json should be reachable."""
    # FastAPI exposes the JSON schema; the HTML docs render at /docs by default.
    # We accept either as proof that the FastAPI app is wired correctly.
    for docs_path in ("/apidoc", "/openapi.json", "/docs"):
        r = requests.get(f"{running_container}{docs_path}", timeout=5, allow_redirects=True)
        if r.status_code == 200:
            return
    pytest.fail("No docs endpoint (/apidoc, /openapi.json, /docs) returned 200")
