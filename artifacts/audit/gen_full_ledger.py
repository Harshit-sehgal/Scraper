#!/usr/bin/env python3
"""Generate the Phase 0 file inventory and per-file audit ledger.

This script intentionally lists every file in the checkout, including
vendor, cache, generated, binary, archive, and log files. Project-owned
text files are opened and scanned in full. Skipped files are still
listed with a concrete skip reason, size, and SHA-256.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDIT_DIR = REPO / "artifacts" / "audit"
OUT_INV = AUDIT_DIR / "FILE_INVENTORY.md"
OUT_CSV = AUDIT_DIR / "FILE_AUDIT_LEDGER.csv"
OUT_MD = AUDIT_DIR / "FILE_AUDIT_LEDGER.md"

CLASSIFICATIONS = [
    "backend_source",
    "frontend_source",
    "test",
    "script",
    "config",
    "documentation",
    "docker_deployment",
    "database_migration",
    "asset",
    "generated",
    "vendor",
    "cache",
    "binary",
    "archive",
    "log",
    "unknown",
]

SKIPPED_CLASSIFICATIONS = {"vendor", "cache", "generated", "binary", "archive", "log"}

LOCKFILE_NAMES = {
    "package-lock.json",
    "uv.lock",
    "poetry.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pip-tools.lock",
}

TEXT_EXTS = {
    "",
    ".bandit",
    ".bash",
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".dockerignore",
    ".env",
    ".example",
    ".gitignore",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".lock",
    ".mjs",
    ".md",
    ".py",
    ".rst",
    ".sample",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}

BINARY_EXTS = {
    ".db",
    ".dll",
    ".dylib",
    ".eot",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".pyo",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
}

ARCHIVE_EXTS = {".7z", ".docx", ".gz", ".tar", ".tgz", ".whl", ".zip"}

STATUS_DOCS = {
    "PROJECT_STATUS.md",
    "docs/CURRENT_STATUS.md",
    "docs/PRODUCTION_READINESS.md",
    "docs/ROADMAP.md",
    "Instructions_for_ai/DataForge_100_100_SaaS_Master_Plan.md",
    "Instructions_for_ai/DataForge_Coding_Agent_100_100_Prompt.txt",
    "Instructions_for_ai/PROGRESS.md",
}

KNOWN_FILE_ISSUES: dict[str, tuple[str, str]] = {
    "backend/app/models.py": (
        "Full pytest and pyflakes identify duplicate AuthProfile definitions and model/test mismatch: missing usage_count/storage_state behavior expected by tests.",
        "Phase 2/4 should reconcile AuthProfile models with tests before claiming full backend suite green.",
    ),
    "backend/app/url_analyzer.py": (
        "Pyflakes/ruff report an unused local variable named parsed at line 478.",
        "Remove or use the variable in a focused lint cleanup after the audit baseline.",
    ),
    "backend/app/routers/auth_profiles.py": (
        "Pyflakes/ruff report unused AuthProfileStatus import; related auth-profile tests fail against the current model.",
        "Reconcile router/model contract and remove unused imports in a focused fix.",
    ),
    "backend/app/saas/router.py": (
        "Pyflakes/ruff report unused User/UserStatus imports; route auth matrix flags user-level mutation routes for review.",
        "Review SaaS mutation authorization semantics and remove unused imports in a focused fix.",
    ),
    "backend/tests/test_auth_profiles.py": (
        "Full pytest fails two assertions in this file: missing usage_count and storage_state exposure mismatch.",
        "Update code or tests after deciding the intended AuthProfile contract.",
    ),
    "backend/tests/test_scheduled_monitoring.py": (
        "Full pytest fails because LocalASGIClient has no put() helper for update tests; pyflakes also reports unused pytest import.",
        "Add client verb support or adjust tests in a focused test infrastructure fix.",
    ),
    "backend/tests/test_workflow.py": (
        "Full pytest fails because LocalASGIClient has no put() helper for update tests.",
        "Add client verb support or adjust tests in a focused test infrastructure fix.",
    ),
    "backend/tests/test_pyflakes_fixes.py": (
        "Full pytest fails because pyflakes currently reports seven warnings/errors.",
        "Run a lint cleanup after preserving this baseline evidence.",
    ),
    "backend/tests/test_route_auth_matrix_generator.py": (
        "Full pytest fails: route-auth-matrix generator flags POST /api/saas/orgs, POST /api/saas/projects, and POST /api/saas/signup as user-level mutation routes needing review.",
        "Decide whether these routes should be operator/admin-only or explicitly allowlisted with documented rationale.",
    ),
    "frontend/styles.css": (
        "npm run lint:js reports Prettier formatting drift in this file.",
        "Run the formatter in a focused frontend formatting cleanup.",
    ),
}


def relpath(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def ext_of(rel: str) -> str:
    return Path(rel).suffix.lower()


def has_part(rel: str, names: set[str]) -> bool:
    return bool(set(rel.split("/")) & names)


def starts_any(rel: str, prefixes: tuple[str, ...]) -> bool:
    return any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in prefixes)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def is_lockfile(rel: str) -> bool:
    name = Path(rel).name
    return name in LOCKFILE_NAMES or ext_of(rel) == ".lock"


def classify(rel: str) -> tuple[str, str, str, bool, str]:
    """Return classification, purpose seed, skip reason, owned, confidence."""
    path = Path(rel)
    name = path.name
    ext = path.suffix.lower()
    parts = rel.split("/")

    if rel.startswith(".git/"):
        return "cache", "Git repository metadata", "git metadata; not project source", False, "high"
    if starts_any(rel, (".codex/", ".agents/", ".kilo/")):
        if "node_modules" in parts:
            return "vendor", "local tooling dependency", "vendor dependency under local tooling state", False, "high"
        return "cache", "local agent/tooling state", "local tooling state; not DataForge product source", False, "medium"
    if has_part(rel, {"node_modules", ".venv", "venv"}):
        return "vendor", "third-party dependency", "vendor dependency; not deep-inspected", False, "high"
    if has_part(rel, {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".vite"}):
        return "cache", "tool cache", "tool cache; not deep-inspected", False, "high"
    if starts_any(rel, ("playwright-report/", "test-results/")):
        return "generated", "test report artifact", "generated test report; not deep-inspected", False, "high"
    if starts_any(rel, ("frontend/dist/", "dist/", "build/")):
        return "generated", "build output", "build output; not deep-inspected", False, "high"
    if starts_any(rel, ("artifacts/validation/", "logs/", "backend/logs/")) or ext == ".log":
        return "log", "validation/runtime log", "log artifact; not deep-inspected", False, "high"
    if rel in {"coverage.json", ".coverage", "backend/.coverage"} or starts_any(rel, ("coverage/",)):
        return "generated", "coverage artifact", "coverage artifact; not deep-inspected", False, "high"
    if starts_any(rel, ("backend/dataforge_scraper.egg-info/",)):
        return "generated", "Python packaging metadata", "generated package metadata; not deep-inspected", False, "high"
    if rel.startswith("artifacts/audit/") and name not in {
        "gen_full_ledger.py",
        "gen_audit_ledger.py",
        "gen_inventory.py",
    }:
        return "generated", "audit report artifact", "generated audit report; current row records pre-regeneration metadata", False, "high"
    if starts_any(rel, ("backend/data/", "backend/backend/data/", "data/")):
        return "generated", "runtime data/checkpoint artifact", "runtime/generated data; not deep-inspected", False, "medium"
    if ext in ARCHIVE_EXTS:
        return "archive", "archive or office document", "archive/binary package; not deep-inspected", False, "high"
    if ext in BINARY_EXTS:
        return "binary", "binary file", "binary file; not deep-inspected", False, "high"
    if name in {"Dockerfile", "nginx.conf"} or name.startswith("docker-compose"):
        return "docker_deployment", "container/deployment configuration", "", True, "high"
    if name in {"prometheus.yml", "prometheus_web.yml", "prometheus_alerts.yml", "alertmanager.yml"}:
        return "docker_deployment", "monitoring/deployment configuration", "", True, "high"
    if rel.startswith("grafana/"):
        return "docker_deployment", "Grafana provisioning/dashboard file", "", True, "high"
    if rel.startswith("backend/init-db/") or ext == ".sql":
        return "database_migration", "database initialization/migration file", "", True, "high"
    if rel.startswith("backend/app/") and ext == ".py":
        return "backend_source", "FastAPI/backend Python source", "", True, "high"
    if rel.startswith("backend/forge_kernel/") and ext == ".py":
        return "backend_source", "Forge kernel backend Python source", "", True, "high"
    if rel.startswith(("backend/tests/", "backend/benchmarks/")):
        return "test", "backend test or fixture", "", True, "high"
    if rel.startswith(("frontend/e2e/", "frontend/smoke/")):
        return "test", "frontend end-to-end/smoke test", "", True, "high"
    if rel.startswith("frontend/"):
        if ext in {".html", ".css", ".js", ".mjs", ".ts", ".svg"}:
            return "frontend_source", "frontend source/asset", "", True, "high"
        if ext in {".json", ".yaml", ".yml"}:
            return "config", "frontend tooling configuration", "", True, "high"
    if rel.startswith("scripts/") or name in {"architecture_validator.py", "verify_compile.py"}:
        return "script", "developer/ops script", "", True, "high"
    if rel.startswith("artifacts/audit/") and ext == ".py":
        return "script", "audit generation script", "", True, "high"
    if rel.startswith("artifacts/") and ext == ".py":
        return "script", "audit/validation helper script", "", True, "high"
    if rel.startswith(("docs/", "Instructions_for_ai/")):
        return "documentation", "project documentation", "", True, "high"
    if name in {
        "AGENTS.md",
        "CHANGELOG.md",
        "CODE_REVIEW_BUGS.md",
        "LICENSE",
        "PROJECT_STATUS.md",
        "README.md",
        "THIRD_PARTY_NOTICES.md",
    }:
        return "documentation", "root project documentation", "", True, "high"
    if is_lockfile(rel):
        return "config", "lockfile pinning transitive dependencies", "machine-generated lockfile; not deep-inspected", True, "high"
    if name == ".bandit" or name.startswith(".env") or ext in {".cfg", ".conf", ".ini", ".json", ".toml", ".yaml", ".yml"} or name in {".dockerignore", ".gitignore", ".pre-commit-config.yaml", ".prettierignore", ".prettierrc", ".stylelintrc.json", "Makefile", "package.json", "pyproject.toml"} or rel.startswith((".github/", ".vscode/")):
        return "config", "project/tooling configuration", "", True, "high"
    if ext in {".csv", ".md", ".rst", ".txt"}:
        return "documentation", "text documentation/data", "", True, "medium"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp"}:
        return "asset", "project visual asset", "visual asset; not deep-inspected", True, "medium"

    return "unknown", "unclassified file", "unclassified; needs follow-up", True, "low"


def walk_repo() -> Iterable[Path]:
    for root, dirs, files in os.walk(REPO):
        dirs[:] = sorted(dirs)
        for filename in sorted(files):
            yield Path(root) / filename


def read_text(path: Path) -> tuple[str, str]:
    try:
        return path.read_text(encoding="utf-8"), ""
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), "utf-8 replacement characters used"
        except OSError as exc:
            return "", f"read error: {exc}"
    except OSError as exc:
        return "", f"read error: {exc}"


def first_heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def summarize_python(text: str) -> str:
    try:
        module = ast.parse(text)
    except SyntaxError:
        return "Python text inspected; AST parse failed."
    doc = ast.get_docstring(module) or ""
    classes = sum(isinstance(node, ast.ClassDef) for node in module.body)
    funcs = sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in module.body)
    stem = doc.splitlines()[0].strip() if doc else "Python module"
    return f"{stem} Top-level classes={classes}, functions={funcs}."


SIGNAL_PATTERNS = [
    ("auth/session/API key", re.compile(r"\b(auth|session|api[_ -]?key|bearer|rbac)\b", re.IGNORECASE)),
    ("tenant/org/project isolation", re.compile(r"\b(tenant|org_id|project_id|owner_id|membership)\b", re.IGNORECASE)),
    ("billing/quota/usage", re.compile(r"\b(billing|invoice|quota|usage|meter)\b", re.IGNORECASE)),
    ("export/recycle/audit", re.compile(r"\b(export|recycle|audit)\b", re.IGNORECASE)),
    ("URL safety/session URL", re.compile(r"\b(ssrf|url_safety|denylist|session_url|localhost|private ip)\b", re.IGNORECASE)),
    ("Playwright/browser", re.compile(r"\b(playwright|browser|storage_state)\b", re.IGNORECASE)),
    ("network capture", re.compile(r"\b(network|request|response|har)\b", re.IGNORECASE)),
    ("pagination/search forms", re.compile(r"\b(pagination|infinite scroll|search_params|form)\b", re.IGNORECASE)),
    ("research/experimental", re.compile(r"\b(research|experimental|DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES)\b", re.IGNORECASE)),
    ("deployment/ops", re.compile(r"\b(docker|compose|prometheus|grafana|nginx|tls|backup|restore)\b", re.IGNORECASE)),
]


def detect_signals(text: str) -> str:
    signals = [name for name, pattern in SIGNAL_PATTERNS if pattern.search(text)]
    return ", ".join(signals[:6]) if signals else "no tracked Phase 0 signal keywords"


def inspect_file(path: Path, rel: str, classification: str, purpose_seed: str, skip: str) -> tuple[str, str, str, str, str]:
    """Return purpose, findings, issues, recommendation, follow-up."""
    issue = KNOWN_FILE_ISSUES.get(rel)
    if issue:
        issues, recommendation = issue
        follow = "yes"
    elif rel in STATUS_DOCS:
        issues = "Documentation contains historical or aspirational readiness claims that current validation does not fully reproduce."
        recommendation = "Treat as historical unless claims are reproduced by fresh commands."
        follow = "yes"
    else:
        issues = "No file-specific issue recorded in Phase 0."
        recommendation = "Keep; inspect this file again before making related changes."
        follow = "no"

    if skip:
        findings = f"Skipped deep inspection: {skip}. Size and SHA-256 recorded."
        return purpose_seed, findings, issues, recommendation, follow

    text, read_note = read_text(path)
    if read_note:
        findings = f"Attempted text inspection; {read_note}."
        if not issue:
            issues = read_note
            recommendation = "Re-check file encoding or classification before editing."
            follow = "yes"
        return purpose_seed, findings, issues, recommendation, follow

    lines = text.count("\n") + (1 if text else 0)
    if ext_of(rel) == ".py":
        purpose = summarize_python(text)
    elif ext_of(rel) in {".md", ".rst"}:
        heading = first_heading(text)
        purpose = heading or purpose_seed
    elif classification == "config":
        purpose = purpose_seed
    elif classification == "frontend_source":
        purpose = f"{purpose_seed}; frontend text file"
    elif classification == "test":
        purpose = f"{purpose_seed}; test/fixture text file"
    else:
        purpose = purpose_seed

    signals = detect_signals(text)
    findings = f"Deep-inspected as text ({lines} lines, {len(text)} chars). Signals: {signals}."
    return purpose, findings, issues, recommendation, follow


def md_escape(value: object) -> str:
    text = str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def main() -> int:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str | int]] = []
    tier_counter: Counter[str] = Counter()
    owned_counter: Counter[str] = Counter()
    deep_counter: Counter[str] = Counter()
    skipped_counter: Counter[str] = Counter()
    ext_counter: Counter[str] = Counter()
    top_counter: Counter[str] = Counter()

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    for idx, abspath in enumerate(walk_repo(), start=1):
        rel = relpath(abspath)
        classification, purpose_seed, skip, owned, confidence = classify(rel)
        ext = ext_of(rel) or "(none)"
        size = abspath.stat().st_size if abspath.exists() else 0
        sha = sha256_of(abspath)
        lockfile = is_lockfile(rel)

        if owned and not skip and not lockfile and (
            ext_of(rel) in TEXT_EXTS
            or Path(rel).name.startswith(".env")
            or classification
            in {
                "backend_source",
                "config",
                "database_migration",
                "docker_deployment",
                "documentation",
                "frontend_source",
                "script",
                "test",
            }
        ):
            deep = True
            purpose, findings, issues, recommendation, follow = inspect_file(abspath, rel, classification, purpose_seed, "")
        else:
            deep = False
            actual_skip = skip or ("machine-generated lockfile; not deep-inspected" if lockfile else "non-text or skipped by classification")
            purpose, findings, issues, recommendation, follow = inspect_file(
                abspath,
                rel,
                classification,
                purpose_seed,
                actual_skip,
            )

        if classification == "unknown":
            follow = "yes"
            if issues == "No file-specific issue recorded in Phase 0.":
                issues = "Unclassified by Phase 0 inventory heuristics."
                recommendation = "Classify this file before making related changes."

        row: dict[str, str | int] = {
            "ledger_id": f"F-{idx:05d}",
            "file_path": rel,
            "file_type": ext,
            "classification": classification,
            "project_owned_yes_no": "yes" if owned else "no",
            "deep_inspected_yes_no": "yes" if deep else "no",
            "skip_reason_if_any": "" if deep else actual_skip,
            "purpose_from_content": purpose,
            "main_findings": findings,
            "issues_found": issues,
            "recommended_action": recommendation,
            "needs_follow_up_yes_no": follow,
            "confidence_level": confidence,
            "size_bytes": size,
            "sha256": sha,
            "sha256_prefix": sha[:12],
            "is_lockfile": "yes" if lockfile else "no",
        }
        rows.append(row)
        tier_counter[classification] += 1
        ext_counter[ext] += 1
        top_counter[rel.split("/", 1)[0]] += 1
        if owned:
            owned_counter[classification] += 1
        if deep:
            deep_counter[classification] += 1
        else:
            skipped_counter[classification] += 1

    fields = [
        "ledger_id",
        "file_path",
        "file_type",
        "classification",
        "project_owned_yes_no",
        "deep_inspected_yes_no",
        "skip_reason_if_any",
        "purpose_from_content",
        "main_findings",
        "issues_found",
        "recommended_action",
        "needs_follow_up_yes_no",
        "confidence_level",
        "size_bytes",
        "sha256",
        "sha256_prefix",
        "is_lockfile",
    ]

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    owned_total = sum(owned_counter.values())
    deep_total = sum(deep_counter.values())
    skipped_total = sum(skipped_counter.values())
    follow_total = sum(1 for row in rows if row["needs_follow_up_yes_no"] == "yes")

    inv: list[str] = []
    inv.append("# DataForge Scraper - File Inventory\n\n")
    inv.append(f"_Generated: {generated_at} from `{len(rows)}` files in the current checkout._\n\n")
    inv.append("This inventory accounts for every file found by `os.walk()` from the repository root. ")
    inv.append("Project-owned text files were opened and scanned in full. Vendor, cache, generated, binary, archive, and log files were listed but not deep-inspected.\n\n")
    inv.append("## Required Field Coverage\n\n")
    inv.append("The complete per-file records with the required fields live in `FILE_AUDIT_LEDGER.csv`. ")
    inv.append("The Markdown ledger mirrors those rows for human review.\n\n")
    inv.append("## Summary\n\n")
    inv.append("| Metric | Count |\n| --- | ---: |\n")
    inv.append(f"| Total files inventoried | {len(rows)} |\n")
    inv.append(f"| Project-owned files | {owned_total} |\n")
    inv.append(f"| Project-owned files deeply inspected | {deep_total} |\n")
    inv.append(f"| Skipped generated/vendor/binary/cache/log/archive files | {skipped_total} |\n")
    inv.append(f"| Files needing follow-up | {follow_total} |\n\n")
    inv.append("## By Classification\n\n")
    inv.append("| Classification | Total | Project-owned | Deep-inspected | Skipped |\n| --- | ---: | ---: | ---: | ---: |\n")
    for tier in CLASSIFICATIONS:
        count = tier_counter.get(tier, 0)
        inv.append(
            f"| {tier} | {count} | {owned_counter.get(tier, 0)} | "
            f"{deep_counter.get(tier, 0)} | {skipped_counter.get(tier, 0)} |\n"
        )
    inv.append("\n## Top-Level Counts\n\n")
    inv.append("| Top-level path | Files |\n| --- | ---: |\n")
    for top, count in top_counter.most_common():
        inv.append(f"| `{top}/` | {count} |\n")
    inv.append("\n## Extension Counts (top 30)\n\n")
    inv.append("| Extension | Files |\n| --- | ---: |\n")
    for ext, count in ext_counter.most_common(30):
        inv.append(f"| `{ext}` | {count} |\n")
    inv.append("\n## Skip Policy\n\n")
    inv.append("Deep inspection was skipped for vendor dependencies, virtualenv files, Git metadata, cache directories, generated reports, build outputs, runtime data, logs, archives, and binary files. Each skipped file still has a CSV/Markdown row with `skip_reason_if_any`.\n\n")
    inv.append("## See Also\n\n")
    inv.append("- `FILE_AUDIT_LEDGER.csv` - complete machine-readable per-file ledger.\n")
    inv.append("- `FILE_AUDIT_LEDGER.md` - complete human-readable per-file ledger.\n")
    inv.append("- `PROJECT_STRUCTURE_SUMMARY.md` - high-level repository map.\n")
    inv.append("- `PROJECT_UNDERSTANDING.md` - product and codebase understanding.\n")
    inv.append("- `VALIDATION_REPORT.md` - command evidence.\n")
    inv.append("- `DOCS_TRUTH_CHECK.md` - docs-vs-code audit.\n")
    OUT_INV.write_text("".join(inv), encoding="utf-8")

    md: list[str] = []
    md.append("# DataForge Scraper - File Audit Ledger\n\n")
    md.append(f"_Generated: {generated_at} from `{len(rows)}` files in the current checkout._\n\n")
    md.append("This ledger lists every file found in the repository, including skipped vendor/cache/generated/binary/log/archive files. ")
    md.append("The CSV version is canonical for automation and includes the same required fields plus full SHA-256 values.\n\n")
    md.append("## Summary by Classification\n\n")
    md.append("| Classification | Total | Project-owned | Deep-inspected | Skipped |\n| --- | ---: | ---: | ---: | ---: |\n")
    for tier in CLASSIFICATIONS:
        md.append(
            f"| {tier} | {tier_counter.get(tier, 0)} | {owned_counter.get(tier, 0)} | "
            f"{deep_counter.get(tier, 0)} | {skipped_counter.get(tier, 0)} |\n"
        )
    md.append(f"| **Total** | **{len(rows)}** | **{owned_total}** | **{deep_total}** | **{skipped_total}** |\n\n")

    md.append("## Files Needing Follow-Up\n\n")
    md.append("| ledger_id | classification | path | issue | recommended action |\n")
    md.append("| --- | --- | --- | --- | --- |\n")
    for row in rows:
        if row["needs_follow_up_yes_no"] == "yes":
            md.append(
                f"| {row['ledger_id']} | {row['classification']} | `{md_escape(row['file_path'])}` | "
                f"{md_escape(row['issues_found'])} | {md_escape(row['recommended_action'])} |\n"
            )
    md.append("\n## Per-File Ledger\n\n")
    md.append(
        "| ledger_id | file_path | file_type | classification | project_owned_yes_no | "
        "deep_inspected_yes_no | skip_reason_if_any | purpose_from_content | main_findings | "
        "issues_found | recommended_action | needs_follow_up_yes_no | confidence_level | size_bytes | sha256_prefix | is_lockfile |\n"
    )
    md.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |\n")
    for row in rows:
        md.append(
            f"| {row['ledger_id']} | `{md_escape(row['file_path'])}` | `{md_escape(row['file_type'])}` | "
            f"{row['classification']} | {row['project_owned_yes_no']} | {row['deep_inspected_yes_no']} | "
            f"{md_escape(row['skip_reason_if_any'])} | {md_escape(row['purpose_from_content'])} | "
            f"{md_escape(row['main_findings'])} | {md_escape(row['issues_found'])} | "
            f"{md_escape(row['recommended_action'])} | {row['needs_follow_up_yes_no']} | "
            f"{row['confidence_level']} | {row['size_bytes']} | `{row['sha256_prefix']}` | {row['is_lockfile']} |\n"
        )
    OUT_MD.write_text("".join(md), encoding="utf-8")

    for tier in CLASSIFICATIONS:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
