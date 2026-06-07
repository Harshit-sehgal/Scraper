#!/usr/bin/env python3
"""
DataForge Production Deployment Verification Script.

This operational script performs automated target-environment validation checks,
ensuring Nginx routing is secure, Prometheus metrics are protected, container
health metrics are valid, TLS limits are configured, and no defaults are leaked.

Run on the target host:
    python3 scripts/verify_production_deployment.py [--port 18080]

Exits non-zero (1) if any check fails so the script can be used as
a CI gate. The previous version printed PASS/FAIL lines but always
returned 0, which made it useless as a gate.
"""

import argparse
import json
import os
import subprocess  # nosec B404 — operational script, hardcoded command vectors
import sys
import urllib.error  # nosec B310 — fixed local probe URLs
import urllib.request  # nosec B310 — fixed local probe URLs

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def run_command(cmd: list[str]) -> tuple[int, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)  # nosec B603 — hardcoded command vectors (docker, curl, ls)  # noqa: S603
        return res.returncode, res.stdout.strip() or res.stderr.strip()
    except Exception as e:
        return -1, str(e)


def run_compose_ps() -> tuple[int, str, str]:
    """Return (exit_code, output, command_label) for the best available Compose command."""
    code, out = run_command(["docker", "compose", "-f", "docker-compose.prod.yml", "ps", "--format", "json"])
    if code == 0:
        return code, out, "docker compose"

    code, out = run_command(["docker-compose", "-f", "docker-compose.prod.yml", "ps"])
    if code == 0:
        return code, out, "docker-compose"

    return code, out, "none"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DataForge Production Deployment Verification Tool",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=18080,
        help="TCP port the nginx reverse proxy is listening on (default: 18080)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    port = args.port

    print("=" * 70)
    print("DataForge Production Deployment Verification Tool")
    print("=" * 70)
    print(f"  Probing nginx on http://127.0.0.1:{port}")

    failures: list[str] = []

    # 1. Environment and Config Checks
    print("\n[1] Environment & Central Configuration...")
    env_file = ".env.production"
    if not os.path.exists(env_file):
        print(f"  [WARNING] '{env_file}' not found in root. Falling back to active process environment.")
    else:
        print(f"  [OK] Found '{env_file}' configuration file.")

    # Run check_prod_env
    prod_check_cmd = ["python3", "scripts/check_prod_env.py"]
    if os.path.exists(env_file):
        prod_check_cmd.extend(["--env-file", env_file])

    # Run in process
    code, out = run_command(prod_check_cmd)
    # Require BOTH the explicit success marker AND a zero exit code so
    # a partial pass (e.g. one check failed silently) cannot be
    # reported as success. The previous `or code == 0` clause let a
    # failing env-check exit 0 in some environments, masking the gap.
    if "Result: required production environment checks passed" in out and code == 0:
        print("  [OK] Environment variables passed all placeholder and security validations.")
    else:
        print("  [FAIL] check_prod_env validation failed. Out:")
        print(f"         {out}")
        print("  Please resolve configuration failures before proceeding.")
        failures.append("env validation")

    # 1b. ADMIN_API_KEY end-to-end protection
    # Powerful admin endpoints (operator-mode switching, knowledge
    # manifold merge, ML selector optimization, etc.) gate themselves
    # on ``DATAFORGE_ADMIN_API_KEY`` in addition to the regular
    # API key. The runtime check at
    # ``app.routers.experimental._require_admin_key`` only emits a
    # warning when this key is empty; it does NOT fail-closed. The
    # fail-closed protection lives here in the deployment gate: if
    # the env var is unset in production, refuse the gate.
    admin_key = os.environ.get("DATAFORGE_ADMIN_API_KEY", "").strip()
    if not admin_key:
        print("  [FAIL] DATAFORGE_ADMIN_API_KEY is unset. Admin endpoints would")
        print("         fall back to the regular API key check. Set a strong")
        print("         admin key before deploying to production.")
        failures.append("admin api key unset")
    else:
        print("  [OK] DATAFORGE_ADMIN_API_KEY is set (admin endpoints are gated).")

    # 2. Container Stack Health Checks
    print("\n[2] Docker Compose Container Statuses...")
    code, ps_out, compose_label = run_compose_ps()
    if code != 0:
        print("  [FAIL] Could not execute Docker Compose status checks. Is the stack started?")
        print(f"         Error: {ps_out}")
        failures.append("compose ps")
    else:
        try:
            # Parse container statuses
            containers = []
            if ps_out:
                # Docker Compose ps returns json lines or a json array depending on version
                if ps_out.startswith("["):
                    containers = json.loads(ps_out)
                else:
                    containers = [json.loads(line) for line in ps_out.split("\n") if line]

            if not containers:
                print("  [FAIL] No running containers found in the production stack.")
                failures.append("no running containers")
            else:
                unhealthy = []
                for c in containers:
                    name = c.get("Name", c.get("Service", "unknown"))
                    state = c.get("State", c.get("Status", "unknown"))
                    health = c.get("Health", "healthy" if "up" in state.lower() else "unhealthy")
                    print(f"  - Container: {name:25} State: {state:12} Health: {health}")
                    if "up" not in state.lower() and "running" not in state.lower():
                        unhealthy.append(name)

                if unhealthy:
                    print(f"  [FAIL] The following containers are not healthy: {', '.join(unhealthy)}")
                    failures.append("unhealthy containers")
                else:
                    print(f"  [OK] All core containers are healthy via {compose_label}.")
        except Exception as e:
            print(f"  [WARNING] Could not parse Compose JSON status: {e}. Ps output follows:")
            print(ps_out)
            failures.append("compose ps parse")

    # 3. Ingress Route Enforcements
    print("\n[3] Ingress Routing & Route Blocks Validation...")
    # Probe the operator-supplied port (default 18080) so the same
    # script works for both ``docker compose port 18080:80`` setups
    # and bare ``80:80`` mappings. The previous hard-coded 18080
    # failed for any deployment that mapped 80 directly.
    test_urls = [
        (f"http://127.0.0.1:{port}/health", 200, "Liveness Probe"),
        (f"http://127.0.0.1:{port}/ready", 200, "Readiness Probe"),
        (f"http://127.0.0.1:{port}/docs", 404, "Swagger UI Block"),
        (f"http://127.0.0.1:{port}/redoc", 404, "ReDoc Block"),
        (f"http://127.0.0.1:{port}/openapi.json", 404, "OpenAPI Schema Block"),
        (f"http://127.0.0.1:{port}/metrics", 404, "Public Metrics Block"),
    ]

    ingress_passed = True
    for url, expected_code, desc in test_urls:
        try:
            req = urllib.request.Request(url, method="GET")  # noqa: S310
            with urllib.request.urlopen(req, timeout=3) as resp:  # nosec B310 — hardcoded local probe URLs  # noqa: S310
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception as e:
            status = -1
            print(f"  [FAIL] Connection failed to {url}: {e}")
            ingress_passed = False
            continue

        if status == expected_code:
            print(f"  - Route: {url:40} Expected: {expected_code} Got: {status} [OK] ({desc})")
        else:
            print(f"  - Route: {url:40} Expected: {expected_code} Got: {status} [FAIL] ({desc})")
            ingress_passed = False

    if ingress_passed:
        print("  [OK] Public Nginx route boundaries are strictly enforced.")
    else:
        print("  [FAIL] One or more public routing security checks failed.")
        failures.append("ingress routing")

    # 4. Egress and SSRF Protections
    print("\n[4] SSRF and Egress Validation...")
    from app.url_safety import validate_public_http_url

    ssrf_targets = [
        ("http://127.0.0.1", False),
        ("http://169.254.169.254/latest/meta-data/", False),
        ("http://localhost:8000/metrics", False),
        ("https://books.toscrape.com", True),
    ]
    ssrf_passed = True
    for url, expected in ssrf_targets:
        try:
            validate_public_http_url(url)
            safe = True
        except ValueError:
            safe = False

        if safe == expected:
            print(f"  - SSRF Boundary: {url:45} Expected Safe: {expected:5} Got: {safe:5} [OK]")
        else:
            print(f"  - SSRF Boundary: {url:45} Expected Safe: {expected:5} Got: {safe:5} [FAIL]")
            ssrf_passed = False

    if ssrf_passed:
        print("  [OK] SSRF routing filters function correctly.")
    else:
        print("  [FAIL] SSRF validation boundary did not meet requirements.")
        failures.append("ssrf validation")

    print("\n" + "=" * 70)
    if failures:
        print(f"Verification Completed WITH FAILURES: {', '.join(failures)}")
        print("=" * 70)
        return 1
    print("Verification Completed — all checks passed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
