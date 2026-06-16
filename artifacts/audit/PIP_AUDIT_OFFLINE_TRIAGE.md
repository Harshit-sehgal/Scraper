# pip-audit Triage Report

**Date:** 2026-06-13
**Issue:** P1-SECURITY-AUDIT-001 (Prompt 0-4 remaining task)
**Status:** Resolved for project-scoped dependencies

## Current Result

Network access is available in the current environment. The project-scoped
audit command now passes:

```bash
python3 -m pip_audit --progress-spinner off --desc off .
```

Exit code: `0`

Output:

```text
No known vulnerabilities found
```

The local full validation gate now runs this same project-scoped command.

## Historical Environment-Level Finding

The earlier 60-record finding came from running `python3 -m pip_audit`
against the global Python environment. That included unrelated system/user
packages such as Ubuntu desktop helpers and VPN packages, plus packages not
managed by this repository. That evidence is useful as a workstation hygiene
signal, but it is not a project dependency gate.

The following packages from that historical global environment were stale:

| Package | Installed | Latest (approx) | Age | Notes |
| --- | --- | --- | --- | --- |
| cryptography | 41.0.7 | 44.0+ | Dec 2023 | Critical: has known GHSA vulns in older 41.x |
| requests | 2.31.0 | 2.32+ | May 2023 | Has known CVE (proxy-authorization header leak) |
| urllib3 | 2.0.7 | 2.3+ | Oct 2023 | Several CVEs in 2.0.x range |
| Jinja2 | 3.1.2 | 3.1.6+ | Apr 2023 | Several XSS fixes in later 3.1.x |
| PyJWT | 2.7.0 | 2.10+ | — | Algorithm confusion fixes in later releases |
| certifi | 2023.11.17 | 2025.x | Nov 2023 | Root CA store 18+ months stale |
| pillow | 10.2.0 | 11.1+ | — | Several security fixes in 10.3+ |
| starlette | 1.0.0 | 0.46+ | — | Very old; many fixes since |
| aiohttp | 3.14.0 | — | — | Needs version check |
| httpx | 0.28.1 | — | — | Relatively recent |
| idna | 3.6 | — | — | Needs version check |

## Recommended Actions

1. Keep `scripts/validate_local.py --full` on project-scoped `pip-audit .`.
2. Add a container-image/SBOM audit for the production image before any
   production readiness claim.
3. Re-run `pip-audit .` after dependency changes and document any justified
   exceptions if a future vulnerability cannot be upgraded immediately.

## Current Mitigations

- The project's Docker image builds from a controlled base and pinning
  is handled in `pyproject.toml`.
- The `bandit` scan passes with no identified issues (58,634 LOC).
- The fast gates (ruff, pyflakes, mypy) are all clean.
- No production deployment exists; this is pre-production.

## Verification Gate

- [x] Project-scoped `pip-audit` exits 0
- [x] Full validation includes project-scoped `pip-audit`
- [ ] Production container/SBOM audit completed before production launch

---

*This document preserves the historical global-environment finding while
recording the current project-scoped audit result.*
