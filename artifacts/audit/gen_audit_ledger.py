#!/usr/bin/env python3
"""Generate FILE_AUDIT_LEDGER.csv and FILE_AUDIT_LEDGER.md from the repository file inventory.

The ledger is the canonical post-fix file-by-file audit trail for the
repository. It augments FILE_INVENTORY.md with a stable ledger id, SHA-256
hash, size in bytes, classification tier (Source / Test / Script / Config /
Frontend / Docs / Docker / Generated / Vendor / Cache / Binary / Unknown),
and a ``is_locked`` flag. The same row is written to both the .csv and the
.md files so they can be cross-referenced.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import subprocess
import sys
from collections import Counter

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_CSV = os.path.join(REPO, "artifacts", "audit", "FILE_AUDIT_LEDGER.csv")
OUT_MD = os.path.join(REPO, "artifacts", "audit", "FILE_AUDIT_LEDGER.md")

# Default exclusions: vendored dependencies and test/lint caches.  The CSV
# includes everything, but the Ledger md report groups them.
EXCLUDE_TOP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "playwright-report",
    "dist",
    "build",
    ".coverage",
    "__pycache__",
}

EXT_BY_TIER = {
    "Python source": {".py"},
    "JavaScript / TypeScript": {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"},
    "Frontend markup": {".html", ".css", ".scss", ".svg"},
    "Markdown / docs": {".md", ".rst", ".txt"},
    "YAML / TOML / JSON": {".yml", ".yaml", ".toml", ".json", ".json5", ".jsonl"},
    "Shell": {".sh", ".bash", ".zsh"},
    "SQL / data": {".sql", ".csv", ".tsv"},
    "Lockfile": {".lock"},
    "Config / env": {".env", ".cfg", ".ini", ".conf"},
}

# Lockfile filenames (no extension) we explicitly tag.
LOCKFILE_NAMES = {
    "package-lock.json",
    "uv.lock",
    "poetry.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
}


def sha256_of(path: str) -> str:
    """Return SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, IOError):
        return ""


def detect_tier(rel: str) -> str:
    """Classify a relative path into a ledger tier."""
    parts = rel.split(os.sep)
    name = os.path.basename(rel)

    # Caches / generated
    if any(p in parts for p in (".mypy_cache", ".ruff_cache", ".pytest_cache", "__pycache__")):
        return "Cache"
    if "playwright-report" in parts:
        return "Generated"
    if name.endswith((".pyc", ".pyo")):
        return "Generated"
    if rel.startswith("artifacts/validation/") and (name.endswith(".log") or name.endswith(".txt") or name.endswith(".json")):
        return "Generated"
    if rel.startswith("artifacts/audit/"):
        return "Generated"  # this very report
    if rel.startswith("backend/data/") or rel.startswith("data/"):
        return "Binary"
    if name.endswith((".sqlite", ".db", ".sqlite3")):
        return "Binary"
    if rel.startswith("coverage/") or rel.startswith(".coverage"):
        return "Generated"
    if rel.startswith("dist/") or rel.startswith("build/"):
        return "Generated"

    # Vendor
    if "node_modules" in parts or ".venv" in parts:
        return "Vendor"

    # Source
    if rel.startswith("backend/app/") and name.endswith(".py"):
        return "Source"
    if rel.startswith("backend/forge_kernel/") and name.endswith(".py"):
        return "Source"

    # Tests
    if rel.startswith("backend/tests/") and name.endswith(".py"):
        return "Test"
    if rel.startswith("backend/benchmarks/") and name.endswith(".py"):
        return "Test"

    # Scripts
    if rel.startswith("scripts/") and name.endswith(".py"):
        return "Script"
    if name in {"architecture_validator.py", "verify_compile.py"} and rel.startswith(os.curdir):
        return "Script"

    # Frontend
    if rel.startswith("frontend/"):
        if name.endswith((".html", ".css", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".scss")):
            return "Frontend"
        if name.endswith(".svg"):
            return "Frontend"
        if name in {"playwright.config.mjs", "vitest.config.js", "package.json"}:
            return "Config"
        if rel.startswith("frontend/node_modules/"):
            return "Vendor"
        return "Frontend"

    # Docs
    if rel.startswith("docs/") or rel.startswith("Instructions_for_ai/"):
        return "Docs"
    if name in {
        "README.md",
        "CHANGELOG.md",
        "CODE_REVIEW_BUGS.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "AGENTS.md",
        "PROJECT_STATUS.md",
    }:
        return "Docs"

    # Config
    if name in {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "uv.lock",
        ".pre-commit-config.yaml",
        ".prettierrc",
        ".prettierignore",
        ".stylelintrc.json",
        ".gitignore",
        "Makefile",
        ".dockerignore",
    }:
        return "Config"
    if name.startswith(".env"):
        return "Config"

    # Docker / deployment
    if name.startswith("docker-compose") or name in {
        "Dockerfile",
        "nginx.conf",
        "prometheus.yml",
        "prometheus_web.yml",
        "prometheus_alerts.yml",
        "alertmanager.yml",
    }:
        return "Docker"
    if rel.startswith("grafana/"):
        return "Docker"
    if rel.startswith(".github/"):
        return "Config"

    # Lockfile heuristic
    if name in LOCKFILE_NAMES:
        return "Config"

    return "Unknown"


def is_locked(rel: str) -> bool:
    """Lockfile detection: only manifests that pin transitive versions count."""
    name = os.path.basename(rel)
    return name in LOCKFILE_NAMES


def get_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def list_files() -> list[str]:
    """Walk the repo and return absolute paths (excluding vendor / cache)."""
    result = []
    for root, dirs, files in os.walk(REPO):
        # Filter excluded top-level dirs in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_TOP_DIRS]
        for f in files:
            result.append(os.path.join(root, f))
    result.sort()
    return result


def short_hash(sha: str, n: int = 12) -> str:
    return sha[:n] if sha else ""


def main() -> int:
    files = list_files()
    rows: list[dict] = []
    tier_counter: Counter[str] = Counter()
    ext_counter: Counter[str] = Counter()

    for idx, abspath in enumerate(files, start=1):
        rel = os.path.relpath(abspath, REPO)
        tier = detect_tier(rel)
        ext = os.path.splitext(rel)[1].lower() or "(no-ext)"
        sha = sha256_of(abspath)
        size = get_size(abspath)
        rows.append(
            {
                "ledger_id": f"F-{idx:05d}",
                "rel_path": rel,
                "tier": tier,
                "extension": ext,
                "size_bytes": size,
                "sha256": short_hash(sha),
                "is_lockfile": "yes" if is_locked(rel) else "no",
            }
        )
        tier_counter[tier] += 1
        ext_counter[ext] += 1

    # Write CSV
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["ledger_id", "rel_path", "tier", "extension", "size_bytes", "sha256", "is_lockfile"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    # Write Markdown
    md = []
    md.append("# DataForge Scraper — File Audit Ledger\n\n")
    md.append(
        f"_Generated: 2026-06-12 from `{len(rows)}` source files "
        "(excludes `.git`, `node_modules`, `.venv`, and tool caches)._\n\n"
    )
    md.append("This ledger is the post-fix canonical file-by-file audit trail. ")
    md.append("Each row is stable across re-runs (SHA-256 of file contents) and ties back to ")
    md.append("`FILE_INVENTORY.md` and `artifacts/audit/ISSUE_LEDGER.md` for cross-referencing.\n\n")

    md.append("## Summary by Tier\n\n")
    md.append("| Tier | Files | % of total |\n")
    md.append("| --- | ---: | ---: |\n")
    total = len(rows)
    for tier in [
        "Source",
        "Test",
        "Script",
        "Frontend",
        "Config",
        "Docker",
        "Docs",
        "Generated",
        "Cache",
        "Vendor",
        "Binary",
        "Unknown",
    ]:
        count = tier_counter.get(tier, 0)
        if count:
            md.append(f"| {tier} | {count} | {count * 100.0 / total:.2f}% |\n")
    md.append(f"| **Total** | **{total}** | **100.00%** |\n\n")

    md.append("## Summary by Extension\n\n")
    md.append("| Extension | Files |\n")
    md.append("| --- | ---: |\n")
    for ext, count in ext_counter.most_common(20):
        md.append(f"| `{ext}` | {count} |\n")
    md.append("\n")

    md.append("## Lockfiles\n\n")
    md.append("| Path | SHA-256 (12) | Size (bytes) |\n")
    md.append("| --- | --- | ---: |\n")
    for row in rows:
        if row["is_lockfile"] == "yes":
            md.append(f"| `{row['rel_path']}` | `{row['sha256']}` | {row['size_bytes']} |\n")
    md.append("\n")

    md.append("## Per-File Ledger (sorted by tier, then path)\n\n")
    md.append("| ledger_id | tier | path | ext | size | sha256[:12] | lockfile |\n")
    md.append("| --- | --- | --- | --- | ---: | --- | :---: |\n")
    for row in sorted(rows, key=lambda r: (r["tier"], r["rel_path"])):
        md.append(
            f"| {row['ledger_id']} | {row['tier']} | `{row['rel_path']}` | `{row['extension']}` "
            f"| {row['size_bytes']} | `{row['sha256']}` | {row['is_lockfile']} |\n"
        )

    with open(OUT_MD, "w") as f:
        f.write("".join(md))

    print(f"Wrote {len(rows)} ledger rows")
    print(f"  CSV: {OUT_CSV}")
    print(f"  MD:  {OUT_MD}")
    print("Tier counts:")
    for tier, count in sorted(tier_counter.items(), key=lambda kv: -kv[1]):
        print(f"  {tier:10s} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
