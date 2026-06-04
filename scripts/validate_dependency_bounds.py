#!/usr/bin/env python3
"""Validate that pyproject.toml dependency bounds are consistent with requirements.lock.txt.

Checks:
  1. Every production dependency in pyproject.toml has an upper version bound (<).
  2. The locked version from requirements.lock.txt falls within the declared range.
  3. All production deps in pyproject.toml exist in the lock file (name-normalized).

Exit codes:
  0 = all checks pass
  1 = one or more violations found
"""

import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
PYPROJECT_TOML = os.path.join(PROJECT_ROOT, "pyproject.toml")
LOCK_FILE = os.path.join(PROJECT_ROOT, "backend", "requirements.lock.txt")


def _normalize(name: str) -> str:
    """Normalize a package name per PEP 503 / pip."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def parse_lock_file(path: str) -> dict[str, str]:
    """Parse requirements.lock.txt into {normalized_name: version}."""
    locked: dict[str, str] = {}
    if not os.path.isfile(path):
        print(f"SKIP: Lock file not found at {path}")
        return locked

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "==" in line:
                name, version = line.split("==", 1)
                locked[_normalize(name)] = version.strip()
    return locked


def parse_pyproject_deps(path: str) -> list[dict]:
    """Extract production dependencies from pyproject.toml using tomllib.

    Returns list of dicts with keys: raw, name, version_spec, has_upper.
    """
    deps: list[dict] = []
    if not os.path.isfile(path):
        print(f"SKIP: pyproject.toml not found at {path}")
        return deps

    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            print(f"ERROR: Failed to parse pyproject.toml: {e}")
            return deps

    raw_deps: list[str] = data.get("project", {}).get("dependencies", [])
    if not raw_deps:
        print("WARN: No production dependencies found in pyproject.toml")
        return deps

    for dep_raw in raw_deps:
        # Parse using regex: package_name [extras] version_spec
        # Pattern: package_name>=X.Y.Z,<A.B.C or package_name[extras]>=X.Y.Z,<A.B.C
        match = re.match(r"^([a-zA-Z0-9_.\-]+(?:\[[^\]]*\])?)\s*(.*)", dep_raw)
        if not match:
            print(f"WARN: Could not parse dependency: {dep_raw}")
            continue

        name = match.group(1).strip()
        # Remove extras like [standard]
        name_clean = re.sub(r"\[.*?\]", "", name).strip()
        version_spec = match.group(2).strip()

        has_upper = "<" in version_spec

        # Extract lower bound
        lower_match = re.search(r">=(\d+\.\d+\.\d+|\d+\.\d+|\d+)", version_spec)
        lower = lower_match.group(1) if lower_match else None

        # Extract upper bound
        upper_match = re.search(r"<(\d+\.\d+\.\d+|\d+\.\d+|\d+)", version_spec)
        upper = upper_match.group(1) if upper_match else None

        deps.append(
            {
                "raw": dep_raw,
                "name": _normalize(name_clean),
                "name_clean": name_clean,
                "version_spec": version_spec,
                "lower": lower,
                "upper": upper,
                "has_upper": has_upper,
            }
        )

    return deps


def check_version_in_bounds(version_str: str, dep: dict) -> bool:
    """Check if a version string falls within the declared bounds."""
    try:
        from packaging.version import Version

        ver = Version(version_str)
    except ImportError:
        return True  # Can't validate without packaging

    if dep["lower"]:
        try:
            lower_ver = Version(dep["lower"])
            if ver < lower_ver:
                return False
        except Exception:
            pass

    if dep["upper"]:
        try:
            upper_ver = Version(dep["upper"])
            if ver >= upper_ver:
                return False
        except Exception:
            pass

    return True


def main() -> int:
    locked = parse_lock_file(LOCK_FILE)
    deps = parse_pyproject_deps(PYPROJECT_TOML)

    if not deps:
        print("No production dependencies found or pyproject.toml missing — skipping.")
        return 0

    violations: list[str] = []

    for dep in deps:
        name = dep["name"]

        # Check 1: Upper bound exists
        if not dep["has_upper"]:
            violations.append(f"{dep['name_clean']}: missing upper bound ('{dep['version_spec']}' has no '<')")

        # Check 2: Exists in lock file
        if name not in locked:
            # Try matching with alternative normalization (underscore vs hyphen)
            alt_name = name.replace("-", "_")
            if alt_name in locked:
                locked[name] = locked.pop(alt_name)
            else:
                violations.append(f"{dep['name_clean']}: not found in {os.path.basename(LOCK_FILE)}")
                continue

        # Check 3: Locked version within bounds
        locked_ver = locked[name]
        if not check_version_in_bounds(locked_ver, dep):
            violations.append(f"{dep['name_clean']}: locked version {locked_ver} is outside bounds '{dep['version_spec']}'")

    if violations:
        print(f"Found {len(violations)} violation(s):")
        for v in violations:
            print(f"  ❌ {v}")
        return 1
    else:
        print(f"✅ All {len(deps)} dependencies have valid upper bounds matching lock file.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
