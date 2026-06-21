# DataForge Scraper — Documentation Index

This page groups every long-form file in `docs/` so you can jump to the
section you need without scrolling through a flat directory of 70+
files. Every entry is **machine-checked**: each file lives on disk, and
its first `# H1` header is reproduced here as written (or trimmed only
for length).

> Want a single canonical answer first? Read
> [`docs/AGENT_TRUTH.md`](AGENT_TRUTH.md). Treat every other doc in
> this index as historical or scoped until you cross-reference it back
> to a fresh `artifacts/validation/` run.

---

## 1. Start here

| File | What it covers |
| --- | --- |
| [`README.md`](../README.md) | Project overview, quick commands, role hierarchy |
| [`AGENT_TRUTH.md`](AGENT_TRUTH.md) | **Single source of truth.** Distinguishes re-verified claims from historical ones. Read this before trusting any other doc. |
| [`SETUP.md`](SETUP.md) | Local development setup |
| [`QUICKSTART.md`](QUICKSTART.md) | Five-minute quickstart |
| [`TUTORIALS.md`](TUTORIALS.md) | Worked examples (extract, paginate, save, export) |
| [`HELP.md`](HELP.md) | FAQ and support pointers |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution conventions |
| [`../AGENTS.md`](../AGENTS.md) | Strict agent contract for AI coding agents |

## 2. Architecture & state

| File | What it covers |
| --- | --- |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | C4-style architecture, module dependencies, research/experimental boundary |
| [`PRODUCT_FLOWS.md`](PRODUCT_FLOWS.md) | End-to-end product flows (extract, save, export, RBAC) |
| [`STATE_MODEL.md`](STATE_MODEL.md) | In-memory cache vs persistent store split |
| [`JOB_STATE_MODEL.md`](JOB_STATE_MODEL.md) | Job lifecycle states and transitions |
| [`RUN_JOB_CHARACTERIZATION.md`](RUN_JOB_CHARACTERIZATION.md) | `run_job` decomposition plan / status |
| [`WORKFLOW_REPLAY.md`](WORKFLOW_REPLAY.md) | Replay-buffer semantics |
| [`URL_INTELLIGENCE.md`](URL_INTELLIGENCE.md) | URL safety, SSRF, pagination detection |
| [`MODULE_CLASSIFICATION.md`](MODULE_CLASSIFICATION.md) | Stable vs experimental research classification |

## 3. API surface

| File | What it covers |
| --- | --- |
| [`API.md`](API.md) | Full API overview |
| [`API_STABLE.md`](API_STABLE.md) | Stable API contract (semver-guaranteed) |
| [`API_EXPERIMENTAL.md`](API_EXPERIMENTAL.md) | Experimental API surface |
| [`API_EXPERIMENTAL_DIFF.md`](API_EXPERIMENTAL_DIFF.md) | Diff between stable and experimental |
| [`API_VERSIONING.md`](API_VERSIONING.md) | Versioning, deprecation policy |
| [`API_KEYS.md`](API_KEYS.md) | API key model, rotation, profile/org scoping |
| [`STABLE_VS_EXPERIMENTAL.md`](STABLE_VS_EXPERIMENTAL.md) | The strict boundary (enforced by CI) |

For the current route inventory and auth posture, see
[`ROUTE_INVENTORY.md`](ROUTE_INVENTORY.md) +
[`ROUTE_AUTH_MATRIX.md`](ROUTE_AUTH_MATRIX.md). Both are
regenerated from code by `scripts/generate_route_inventory.py` and
`scripts/generate_route_auth_matrix.py`.

## 4. Auth, tenants, and authorization

| File | What it covers |
| --- | --- |
| [`ROUTE_AUTH_MATRIX.md`](ROUTE_AUTH_MATRIX.md) | Per-route auth dependency + tenant scope (machine-generated) |
| [`ROUTE_INVENTORY.md`](ROUTE_INVENTORY.md) | All routes, methods, and router modules (machine-generated) |
| [`AUTH_PROFILES.md`](AUTH_PROFILES.md) | Authenticated scraping profile model + encryption |
| [`AUTH_TENANT_BOUNDARY.md`](AUTH_TENANT_BOUNDARY.md) | Tenant isolation enforcement |
| [`DASHBOARD_AUTH.md`](DASHBOARD_AUTH.md) | Dashboard auth posture and v2 plan |

## 5. Security, safety, SSRF, TLS

| File | What it covers |
| --- | --- |
| [`SECURITY.md`](SECURITY.md) | Security overview |
| [`SECURITY_MODEL.md`](SECURITY_MODEL.md) | Threat model and trust boundaries |
| [`SECURITY_HEADERS.md`](SECURITY_HEADERS.md) | HTTP security headers |
| [`SSRF_EGRESS.md`](SSRF_EGRESS.md) | SSRF and egress hardening |
| [`TLS_DEPLOYMENT.md`](TLS_DEPLOYMENT.md) | HTTPS / TLS verification playbooks |
| [`SAFETY_AND_ACCEPTABLE_USE.md`](SAFETY_AND_ACCEPTABLE_USE.md) | Non-bypassable safety policy |

## 6. Storage and data

| File | What it covers |
| --- | --- |
| [`STORAGE_SPLIT.md`](STORAGE_SPLIT.md) | Storage cutover plan (in-memory vs persistent) |
| [`STORAGE_BOUNDARIES.md`](STORAGE_BOUNDARIES.md) | What lives where across backends |
| [`DATA_RETENTION.md`](DATA_RETENTION.md) | Retention and deletion policy |
| [`DATA_QUALITY.md`](DATA_QUALITY.md) | Cleaning, validation, dedup, scoring |
| [`EXTRACTION_DEPTH.md`](EXTRACTION_DEPTH.md) | Pagination, infinite scroll, schema fields |
| [`EXTRACTION_QUALITY.md`](EXTRACTION_QUALITY.md) | Quality metrics and benchmarking |

## 7. Validation, testing, quality

| File | What it covers |
| --- | --- |
| [`VALIDATION.md`](VALIDATION.md) | How `scripts/validate_local.py` works |
| [`TESTING.md`](TESTING.md) | Test strategy and conventions |
| [`TEST_RELIABILITY.md`](TEST_RELIABILITY.md) | Flaky-test tracking, reruns, timeouts |
| [`COVERAGE_REPORT.md`](COVERAGE_REPORT.md) | Latest coverage numbers |
| [`CI_STATUS.md`](CI_STATUS.md) | GitHub Actions job status |
| [`CODE_QUALITY.md`](CODE_QUALITY.md) | Coding standards |

## 8. Observability, monitoring, audit

| File | What it covers |
| --- | --- |
| [`MONITORING.md`](MONITORING.md) | Prometheus metrics and SLOs |
| [`OBSERVABILITY.md`](OBSERVABILITY.md) | Logs, traces, metrics baseline |
| [`AUDIT_LOGS.md`](AUDIT_LOGS.md) | Audit-log surface |
| [`CONFIG_AUDIT.md`](CONFIG_AUDIT.md) | Environment-variable audit |
| [`ENV_VARIABLES.md`](ENV_VARIABLES.md) | Reference for every env var |
| [`TELEGRAM_NOTIFICATIONS.md`](TELEGRAM_NOTIFICATIONS.md) | Bot integration |

## 9. Billing, usage, cost

| File | What it covers |
| --- | --- |
| [`SAAS_MODEL.md`](SAAS_MODEL.md) | SaaS posture (still aspirational) |
| [`BILLING.md`](BILLING.md) | Billing endpoints and quotas |
| [`USAGE_AND_BILLING.md`](USAGE_AND_BILLING.md) | Usage metering → billing rollups |
| [`LOAD_AND_COST_CONTROLS.md`](LOAD_AND_COST_CONTROLS.md) | Concurrency caps and cost ceilings |

## 10. Operations, incidents, resilience

| File | What it covers |
| --- | --- |
| [`PRODUCTION.md`](PRODUCTION.md) | Production overview |
| [`PRODUCTION_STARTUP.md`](PRODUCTION_STARTUP.md) | Container startup sequence |
| [`DEPLOYMENT_CHECKLIST.md`](DEPLOYMENT_CHECKLIST.md) | Pre-deploy checklist |
| [`OPS_READINESS_CHECKLIST.md`](OPS_READINESS_CHECKLIST.md) | SRE readiness checks |
| [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) | Release process |
| [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md) | Incident lifecycle |
| [`INCIDENT_RUNBOOK.md`](INCIDENT_RUNBOOK.md) | Concrete runbook |
| [`DISASTER_RECOVERY.md`](DISASTER_RECOVERY.md) | DR plan |
| [`RESILIENCE_PATTERNS.md`](RESILIENCE_PATTERNS.md) | Resilience design patterns |
| [`MIGRATION_AND_ROLLBACK_POLICY.md`](MIGRATION_AND_ROLLBACK_POLICY.md) | Schema and code migration policy |
| [`FAILURE_EXPLANATIONS.md`](FAILURE_EXPLANATIONS.md) | User-facing failure narratives |

## 11. Benchmarks, roadmap, refs

| File | What it covers |
| --- | --- |
| [`BENCHMARKS.md`](BENCHMARKS.md) | Benchmark results |
| [`BENCHMARK_PLAN.md`](BENCHMARK_PLAN.md) | Benchmark methodology |
| [`HANDOFF.md`](HANDOFF.md) | Handoff notes |
| [`LIMITATIONS.md`](LIMITATIONS.md) | Known limitations |

---

## Mapping by user role

- **New contributor** → [`SETUP.md`](SETUP.md) →
  [`CONTRIBUTING.md`](CONTRIBUTING.md) →
  [`CODE_QUALITY.md`](CODE_QUALITY.md) →
  [`ARCHITECTURE.md`](ARCHITECTURE.md)
- **Operator / SRE** → [`PRODUCTION.md`](PRODUCTION.md) →
  [`DEPLOYMENT_CHECKLIST.md`](DEPLOYMENT_CHECKLIST.md) →
  [`MONITORING.md`](MONITORING.md) →
  [`INCIDENT_RUNBOOK.md`](INCIDENT_RUNBOOK.md)
- **Security reviewer** → [`SECURITY_MODEL.md`](SECURITY_MODEL.md) →
  [`SSRF_EGRESS.md`](SSRF_EGRESS.md) →
  [`AUTH_TENANT_BOUNDARY.md`](AUTH_TENANT_BOUNDARY.md) →
  [`SAFETY_AND_ACCEPTABLE_USE.md`](SAFETY_AND_ACCEPTABLE_USE.md)
- **API consumer / dashboard** → [`API.md`](API.md) →
  [`API_KEYS.md`](API_KEYS.md) →
  [`STABLE_VS_EXPERIMENTAL.md`](STABLE_VS_EXPERIMENTAL.md)
- **AI coding agent** → [`../AGENTS.md`](../AGENTS.md) →
  [`AGENT_TRUTH.md`](AGENT_TRUTH.md) (canonical truth source)

---

## How to keep this index honest

- Each file in the table above is verified to exist on disk before
  publication.
- Group thresholds are intentionally loose (this is a navigation aid,
  not a forced taxonomy).
- If you remove a file from `docs/`, update this index in the same
  commit. If you add a file, add it under the most specific group and
  update the role-mapping section.
