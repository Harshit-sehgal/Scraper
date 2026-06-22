# Deliverable 8: Documentation Cleanup Plan

<div style="border: 2px solid #d24646; background: #fef6f6; padding: 1rem 1.2rem; border-radius: 12px; margin-bottom: 1.5rem;">
  <strong style="color: #972a2a; font-size: 0.95rem;">⚠ HISTORICAL DOCUMENT</strong><br>
  <span style="color: #607069; font-size: 0.85rem;">
    This archived deliverable was generated during a prior cleanup cycle. It is preserved for reference only.
    Do not treat it as current evidence. Always consult <code>PROJECT_STATUS.md</code> for the current truth source.
  </span>
</div>


**Date:** May 30, 2026
**Method:** Read all markdown files, classify against evidence.

---

## File Classification

| File | Action | Reason |
|------|--------|--------|
| `README.md` | **Rewrite** | Contains stale claims and overstatements |
| `docs/AGENT_TRUTH.md` | **Rewrite** | Stale test counts (says 1,884 vs actual 2,207), false pass claims |
| `docs/ARCHITECTURE.md` | **Keep** (minor fixes) | Largely accurate, may need minor updates |
| `docs/API.md` | **Keep** | Documented routes match actual routes |
| `docs/SETUP.md` | **Keep** | Setup instructions appear accurate |
| `docs/PRODUCTION.md` | **Keep** (minor fixes) | Production doc needs stale claim fixes |
| `docs/PRODUCTION_STARTUP.md` | **Keep** | Startup guide is accurate |
| `docs/SECURITY.md` | **Keep** (already fixed) | CSP section updated in previous session |
| `docs/LIMITATIONS.md` | **Keep** | Limitations are honest and accurate |
| `docs/HANDOFF.md` | **Archive** | Historical handoff document |
| `docs/AUDIT_INDEX.md` | **Keep** | Navigation index for audit deliverables |
| `docs/audit/DELIVERABLE_*.md` | **Keep** | These are the current audit deliverables |
| `docs/archive/` | **Review** | 12 files — see below |

---

## Archive Files

| File | Action | Reason |
|------|--------|--------|
| `docs/archive/RELEASE_NOTES.md` | ✅ **Already deleted** | Removed during 2026-06-22 cleanup (task 61+) |
| `docs/archive/RELEASE_CANDIDATE_CHECKLIST.md` | ✅ **Already deleted** | Removed during 2026-06-22 cleanup (task 61+) |
| `docs/archive/DEPLOYMENT_VALIDATION_CHECKLIST.md` | ✅ **Already deleted** | Removed during 2026-06-22 cleanup (task 61+) |
| `docs/archive/audit/AUDIT_SUMMARY.md` | ✅ **Already deleted** | Removed during 2026-06-22 cleanup (task 61+) |
| `docs/archive/audit/DELIVERABLE_*.md` (7 remaining) | **Keep** | Historical audit deliverables (D1-D9 excluding D10/D12) |

---

## Proposed Final Docs Structure

```
README.md                                  — Honest project overview
PROJECT_STATUS.md                          — Truth-first status file
docs/
  ARCHITECTURE.md                          — Code-based architecture
  API.md                                   — API reference
  SETUP.md                                 — Setup guide
  PRODUCTION.md                            — Production deployment guide
  PRODUCTION_STARTUP.md                    — Startup checklist
  SECURITY.md                              — Security documentation
  LIMITATIONS.md                           — Known limitations
  AUDIT_INDEX.md                           — Audit deliverables index
  audit/
    DELIVERABLE_1_TRUTH_INVENTORY.md       — File inventory
    DELIVERABLE_2_ARCHITECTURE_MAP.md      — Architecture reality
    DELIVERABLE_3_CLAIMS_AUDIT.md          — Claims vs evidence
    DELIVERABLE_4_ERROR_ISSUE_LIST.md      — Issues found
    DELIVERABLE_5_TEST_TRUTH_REPORT.md     — Test reality
    DELIVERABLE_6_BENCHMARK_TRUTH_REPORT.md— Benchmark reality
    DELIVERABLE_7_SECURITY_REPORT.md       — Security reality
    DELIVERABLE_8_DOCUMENTATION_CLEANUP.md — This plan
    DELIVERABLE_9_CORRECTED_README.md      — New README
    DELIVERABLE_10_PROJECT_STATUS.md       — New PROJECT_STATUS
    DELIVERABLE_11_EXACT_FIX_PLAN.md       — Ordered fix plan
    DELIVERABLE_12_FINAL_TRUTH_CHART.md    — Honest progress chart
  archive/
    audit/                                 — Historical D1-D9 (D10/D12 excluded)
      DELIVERABLE_1_*.md through DELIVERABLE_11_*.md
```

## Documents to Remove/Rewrite

1. ✅ Already deleted: `docs/archive/RELEASE_NOTES.md` (2026-06-22 cleanup)
2. ✅ Already deleted: `docs/archive/RELEASE_CANDIDATE_CHECKLIST.md` (2026-06-22 cleanup)
3. ✅ Already deleted: `docs/archive/DEPLOYMENT_VALIDATION_CHECKLIST.md` (2026-06-22 cleanup)
4. ✅ Already deleted: `docs/archive/audit/AUDIT_SUMMARY.md` (2026-06-22 cleanup)
5. ✏️ Rewrite: `README.md` (see D9)
6. ✏️ Rewrite: `docs/AGENT_TRUTH.md` (see D10)
