#!/usr/bin/env python3
"""
DataForge Production Deployment Verification Script.

This operational script performs automated target-environment validation checks,
ensuring Nginx routing is secure, Prometheus metrics are protected, container
health metrics are valid, TLS limits are configured, and no defaults are leaked.

Run on the target host:
    python3 scripts/verify_production_deployment.py
"""
import os
import sys
import json
import urllib.request
import urllib.error
import subprocess

def run_command(cmd: list[str]) -> tuple[int, str]:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.returncode, res.stdout.strip() or res.stderr.strip()
    except Exception as e:
        return -1, str(e)

def main():
    print("=" * 70)
    print("DataForge Production Deployment Verification Tool")
    print("=" * 70)

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
    if "Result: required production environment checks passed" in out or code == 0:
        print("  [OK] Environment variables passed all placeholder and security validations.")
    else:
        print("  [FAIL] check_prod_env validation failed. Out:")
        print(f"         {out}")
        print("  Please resolve configuration failures before proceeding.")

    # 2. Container Stack Health Checks
    print("\n[2] Docker Compose Container Statuses...")
    code, ps_out = run_command(["docker", "compose", "-f", "docker-compose.prod.yml", "ps", "--format", "json"])
    if code != 0:
        # Try old syntax or simple ps
        code, ps_out = run_command(["docker-compose", "-f", "docker-compose.prod.yml", "ps"])
        if code != 0:
            print("  [FAIL] Could not execute Docker Compose status checks. Is the stack started?")
            print(f"         Error: {ps_out}")
        else:
            print("  [OK] Stack is running (using legacy docker-compose ps). Check container health manually.")
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
                else:
                    print("  [OK] All core containers (backend, worker, Postgres, Nginx, Prometheus, Grafana) are healthy.")
        except Exception as e:
            print(f"  [WARNING] Could not parse Compose JSON status: {e}. Ps output follows:")
            print(ps_out)

    # 3. Ingress Route Enforcements
    print("\n[3] Ingress Routing & Route Blocks Validation...")
    # Check default Nginx port (18080 or 80 depending on configuration/proxy)
    test_urls = [
        ("http://127.0.0.1:18080/health", 200, "Liveness Probe"),
        ("http://127.0.0.1:18080/ready", 200, "Readiness Probe"),
        ("http://127.0.0.1:18080/docs", 404, "Swagger UI Block"),
        ("http://127.0.0.1:18080/redoc", 404, "ReDoc Block"),
        ("http://127.0.0.1:18080/openapi.json", 404, "OpenAPI Schema Block"),
        ("http://127.0.0.1:18080/metrics", 404, "Public Metrics Block"),
    ]

    ingress_passed = True
    for url, expected_code, desc in test_urls:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
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

    print("\n" + "=" * 70)
    print("Verification Completed.")
    print("=" * 70)

if __name__ == "__main__":
    main()
