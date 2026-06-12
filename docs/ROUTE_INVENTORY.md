# Route Inventory

**Generated from the registered FastAPI app. Do not edit generated rows by hand.**

**Generated:** 2026-06-12 21:39:05 UTC
**Command:** `python3 scripts/generate_route_inventory.py`

This inventory distinguishes stable API routes, experimental API routes,
development docs/static routes, health/readiness routes, and session/auth routes.

**Total route rows:** 135

## Stable Api Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/auth-profiles` | `app.routers.auth_profiles` | `list_auth_profiles` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles` | `app.routers.auth_profiles` | `create_auth_profile` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/auth-profiles/{profile_id}` | `app.routers.auth_profiles` | `delete_auth_profile` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/auth-profiles/{profile_id}` | `app.routers.auth_profiles` | `get_auth_profile` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles/{profile_id}/complete-login` | `app.routers.auth_profiles` | `complete_login` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles/{profile_id}/revoke` | `app.routers.auth_profiles` | `revoke_profile` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles/{profile_id}/start-login` | `app.routers.auth_profiles` | `start_login` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/auth-profiles/{profile_id}/validate` | `app.routers.auth_profiles` | `validate_profile` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/discover` | `app.routers.jobs_write` | `discover` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `POST` | `/api/exports/batch` | `app.routers.exports` | `batch_export` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/intelligence/analyze-url` | `app.routers.intelligence` | `analyze_url_endpoint` | stable | protected | authenticated-user |  |  |  | protected by global /api middleware; no route-level role dependency |
| `GET` | `/api/jobs` | `app.routers.jobs_read` | `list_jobs` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs` | `app.routers.jobs_write` | `create_job` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `DELETE` | `/api/jobs/cleanup/terminal` | `app.routers.jobs_write` | `clear_terminal_jobs` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `DELETE` | `/api/jobs/{job_id}` | `app.routers.jobs_write` | `delete_job` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `GET` | `/api/jobs/{job_id}` | `app.routers.jobs_read` | `get_job` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs/{job_id}/backfill-metadata` | `app.routers.jobs_write` | `backfill_job_metadata` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `POST` | `/api/jobs/{job_id}/cancel` | `app.routers.jobs_write` | `cancel_job` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/events` | `app.routers.jobs_read` | `get_job_events` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `GET` | `/api/jobs/{job_id}/export/csv` | `app.routers.exports` | `export_csv` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/export/excel` | `app.routers.exports` | `export_excel` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/export/json` | `app.routers.exports` | `export_json` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/jobs/{job_id}/reclean` | `app.routers.jobs_write` | `reclean_job` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/results` | `app.routers.jobs_read` | `get_job_results` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `DELETE` | `/api/operator/denylist` | `app.routers.operator` | `remove_denylist_entry` | stable | protected | admin | require_role_with_user |  | dict | require_role/admin-only dependency |
| `GET` | `/api/operator/denylist` | `app.routers.operator` | `list_denylist` | stable | protected | operator-or-admin | require_role_with_user |  | list | route dependency accepts admin/operator |
| `POST` | `/api/operator/denylist` | `app.routers.operator` | `add_denylist_entry` | stable | protected | admin | require_role_with_user |  | DenylistEntryResponse | require_role/admin-only dependency |
| `DELETE` | `/api/recycle_bin` | `app.routers.jobs_write` | `clear_recycle_bin` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `GET` | `/api/recycle_bin` | `app.routers.jobs_read` | `list_recycle_bin` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `DELETE` | `/api/recycle_bin/{job_id}` | `app.routers.jobs_write` | `hard_delete_job` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `POST` | `/api/recycle_bin/{job_id}/restore` | `app.routers.jobs_write` | `restore_job` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `POST` | `/api/saas/aup/accept` | `app.saas.router` | `accept_aup` | stable | protected | authenticated-user | require_role_with_user |  | AupStatusResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/aup/status` | `app.saas.router` | `get_aup_status` | stable | protected | authenticated-user | require_role_with_user |  | AupStatusResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/me` | `app.saas.router` | `get_my_profile` | stable | protected | authenticated-user | require_role_with_user |  | UserProfileResponse | route dependency accepts admin/operator/user |
| `DELETE` | `/api/saas/memberships/{membership_id}` | `app.saas.router` | `remove_member` | stable | protected | operator-or-admin | require_role_with_user |  |  | route dependency accepts admin/operator |
| `GET` | `/api/saas/orgs` | `app.saas.router` | `list_my_organizations` | stable | protected | authenticated-user | require_role_with_user |  | OrgListResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/orgs` | `app.saas.router` | `create_organization` | stable | protected | operator-or-admin | require_role_with_user |  | OrgResponse | route dependency accepts admin/operator |
| `GET` | `/api/saas/orgs/{org_id}` | `app.saas.router` | `get_organization` | stable | protected | authenticated-user | require_role_with_user |  | OrgResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/orgs/{org_id}/members` | `app.saas.router` | `list_org_members` | stable | protected | authenticated-user | require_role_with_user |  | list | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/orgs/{org_id}/projects` | `app.saas.router` | `list_org_projects` | stable | protected | authenticated-user | require_role_with_user |  | ProjectListResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/plan` | `app.saas.router` | `get_plan_info` | stable | protected | authenticated-user | require_role_with_user |  | PlanInfoResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/projects` | `app.saas.router` | `create_project` | stable | protected | operator-or-admin | require_role_with_user |  | ProjectResponse | route dependency accepts admin/operator |
| `GET` | `/api/saas/projects/{project_id}` | `app.saas.router` | `get_project` | stable | protected | authenticated-user | require_role_with_user |  | ProjectResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/projects/{project_id}/keys` | `app.saas.router` | `list_project_api_keys` | stable | protected | authenticated-user | require_role_with_user |  | ApiKeyListResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/projects/{project_id}/keys` | `app.saas.router` | `create_api_key` | stable | protected | operator-or-admin | require_role_with_user |  | ApiKeyCreateResponse | route dependency accepts admin/operator |
| `DELETE` | `/api/saas/projects/{project_id}/keys/{key_id}` | `app.saas.router` | `revoke_api_key` | stable | protected | operator-or-admin | require_role_with_user |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scheduled` | `app.routers.scheduled_monitoring` | `list_scheduled_jobs` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/scheduled` | `app.routers.scheduled_monitoring` | `create_scheduled_job` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `DELETE` | `/api/scheduled/{job_id}` | `app.routers.scheduled_monitoring` | `delete_scheduled_job` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scheduled/{job_id}` | `app.routers.scheduled_monitoring` | `get_scheduled_job` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `PUT` | `/api/scheduled/{job_id}` | `app.routers.scheduled_monitoring` | `update_scheduled_job` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scheduled/{job_id}/changes` | `app.routers.scheduled_monitoring` | `detect_changes` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/schema/suggest` | `app.routers.jobs_write` | `suggest_schema` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/browser` | `app.routers.scraper` | `get_browser_stats` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/config` | `app.routers.scraper` | `get_scraper_config` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `POST` | `/api/scraper/diagnostics` | `app.routers.scraper` | `get_scraper_diagnostics` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/health/legacy` | `app.routers.scraper` | `get_legacy_domain_health` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/memory/stats` | `app.routers.scraper` | `get_selector_memory_brief` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/regressions` | `app.routers.scraper` | `get_regression_archive` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `POST` | `/api/scraper/regressions/generate-all-tests` | `app.routers.scraper` | `generate_all_replay_tests` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/regressions/{entry_id}` | `app.routers.scraper` | `get_regression_detail` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `POST` | `/api/scraper/regressions/{entry_id}/generate-test` | `app.routers.scraper` | `generate_regression_replay_test` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `POST` | `/api/scraper/selectors/cleanup` | `app.routers.scraper` | `trigger_selector_cleanup` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/selectors/domain/{domain}` | `app.routers.scraper` | `get_domain_selector_confidence` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/selectors/low-confidence` | `app.routers.scraper` | `get_low_confidence_selectors` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/selectors/stats` | `app.routers.scraper` | `get_selector_memory_stats` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/stats` | `app.routers.scraper` | `get_scraper_stats` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `DELETE` | `/api/scraper/telemetry` | `app.routers.scraper` | `clear_telemetry` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/telemetry` | `app.routers.scraper` | `get_recent_telemetry` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `POST` | `/api/system/csp-violations` | `app.routers.system` | `csp_violations` | stable | public |  |  |  |  | explicit API middleware exemption |
| `GET` | `/api/system/diagnostics/export` | `app.routers.system` | `export_system_diagnostics` | stable | protected | admin | require_role |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/rate-limit-stats` | `app.routers.system` | `rate_limit_stats` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/system/status` | `app.routers.system` | `system_status` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `GET` | `/api/system/storage/status` | `app.routers.system` | `storage_status` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `POST` | `/api/url/analyze` | `app.routers.system` | `analyze_url` | stable | protected | operator-or-admin | require_role |  |  | route dependency accepts admin/operator |
| `POST` | `/api/workflow-drafts/from-url-analysis` | `app.routers.workflow` | `create_workflow_draft_from_url_analysis` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/workflow-drafts/{draft_id}/detect-fields` | `app.routers.workflow` | `detect_workflow_draft_fields` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/workflow-drafts/{draft_id}/manual-mapping` | `app.routers.workflow` | `create_workflow_from_manual_mapping` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/workflows` | `app.routers.workflow` | `list_workflows` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/workflows` | `app.routers.workflow` | `create_workflow` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `DELETE` | `/api/workflows/{workflow_id}` | `app.routers.workflow` | `delete_workflow` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/workflows/{workflow_id}` | `app.routers.workflow` | `get_workflow` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `PATCH` | `/api/workflows/{workflow_id}` | `app.routers.workflow` | `patch_workflow` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `PUT` | `/api/workflows/{workflow_id}` | `app.routers.workflow` | `update_workflow` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/workflows/{workflow_id}/preview` | `app.routers.workflow` | `preview_workflow` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/workflows/{workflow_id}/run` | `app.routers.workflow` | `run_workflow` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |

## Experimental Api Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/operator/dashboard` | `app.routers.experimental` | `get_system_dashboard` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/operator/health` | `app.routers.experimental` | `get_operator_health_summary` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/operator/mode` | `app.routers.experimental` | `get_current_mode` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `POST` | `/api/operator/mode` | `app.routers.experimental` | `set_operator_mode` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/operator/predictions` | `app.routers.experimental` | `get_degradation_predictions` | experimental | protected | authenticated-user | require_role, verify_experimental_enabled |  |  | route dependency accepts admin/operator/user |
| `GET` | `/api/operator/predictions/{domain}` | `app.routers.experimental` | `get_domain_prediction` | experimental | protected | authenticated-user | require_role, verify_experimental_enabled |  |  | route dependency accepts admin/operator/user |
| `GET` | `/api/scraper/economics` | `app.routers.experimental` | `get_extraction_economics` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/domain/{domain}` | `app.routers.experimental` | `get_domain_health` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/domains` | `app.routers.experimental` | `get_all_domains_health` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/summary` | `app.routers.experimental` | `get_system_health_summary` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `POST` | `/api/scraper/ml/learn` | `app.routers.experimental` | `record_selector_learning` | experimental | protected | operator-or-admin | require_role, verify_experimental_enabled |  |  | route dependency accepts admin/operator |
| `POST` | `/api/scraper/ml/optimize/domain/{domain}` | `app.routers.experimental` | `optimize_domain_selectors` | experimental | protected | operator-or-admin | require_role, verify_experimental_enabled |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/ml/optimize/domain/{domain}/history` | `app.routers.experimental` | `get_optimization_history` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/strategy/domain/{domain}` | `app.routers.experimental` | `get_domain_strategy_analysis` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `POST` | `/api/scraper/strategy/evolve/{domain}` | `app.routers.experimental` | `evolve_domain_strategy` | experimental | protected | operator-or-admin | require_role, verify_experimental_enabled |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/strategy/recommend/{domain}` | `app.routers.experimental` | `recommend_fetch_strategy` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `POST` | `/api/scraper/strategy/record` | `app.routers.experimental` | `record_strategy_attempt` | experimental | protected | operator-or-admin | require_role, verify_experimental_enabled |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scraper/strategy/report` | `app.routers.experimental` | `get_all_strategies_report` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/trends` | `app.routers.experimental` | `get_extraction_trends` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/scraper/trends/{domain}` | `app.routers.experimental` | `get_domain_trend` | experimental | protected | authenticated-user | require_role, verify_experimental_enabled |  |  | route dependency accepts admin/operator/user |
| `GET` | `/api/system/acquisition/telemetry` | `app.routers.experimental` | `acquisition_telemetry` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/agency` | `app.routers.experimental` | `system_agency` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/crystalline` | `app.routers.experimental` | `system_crystalline` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/domain-policy` | `app.routers.experimental` | `system_domain_policy` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/export/knowledge` | `app.routers.experimental` | `export_knowledge` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/history/topology` | `app.routers.experimental` | `system_topology_history` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `POST` | `/api/system/merge/knowledge` | `app.routers.experimental` | `merge_knowledge` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/observability` | `app.routers.experimental` | `system_observability` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `POST` | `/api/system/refactor/compress` | `app.routers.experimental` | `trigger_manifold_compression` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/replay/chain` | `app.routers.experimental` | `system_replay_chains` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/replay/events` | `app.routers.experimental` | `system_replay_events` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/replay/status` | `app.routers.experimental` | `system_replay_status` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `POST` | `/api/system/scheduler/step` | `app.routers.experimental` | `process_cognitive_tasks` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/search` | `app.routers.experimental` | `system_search` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/topology` | `app.routers.experimental` | `system_topology` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |

## Session/Auth Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/api/saas/signup` | `app.saas.router` | `signup` | stable | public |  |  |  | SignupResponse | explicit API middleware exemption |
| `DELETE` | `/api/session` | `app.routers.session` | `destroy_session` | stable | public |  |  |  |  | explicit API middleware exemption |
| `POST` | `/api/session` | `app.routers.session` | `create_session` | stable | public |  |  |  |  | explicit API middleware exemption |
| `GET` | `/api/session/me` | `app.routers.session` | `get_session` | stable | public |  |  |  |  | explicit API middleware exemption |

## Health/Readiness Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/` | `app.routers.health` | `root` | stable | public |  |  |  |  | non-API probe/static route |
| `MOUNT` | `/app` | `starlette.routing` | `Mount` | stable | public |  |  |  |  | mounted ASGI/static route |
| `GET` | `/health` | `app.routers.health` | `health` | stable | public |  |  |  |  | non-API probe/static route |
| `GET` | `/metrics` | `app.routers.system` | `metrics` | stable | protected | metrics-token-if-configured |  |  |  | settings.METRICS_TOKEN check in endpoint |
| `GET` | `/ready` | `app.routers.health` | `ready` | stable | public |  |  |  |  | non-API probe/static route |

## Docs/Openapi/Static/Dev Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `MOUNT` | `/dashboard` | `starlette.routing` | `Mount` | stable | public |  |  |  |  | mounted ASGI/static route |
| `GET` | `/docs` | `fastapi.applications` | `swagger_ui_html` | stable | public-dev-only | development-docs |  |  |  | FastAPI docs disabled by app config in production |
| `GET` | `/docs/oauth2-redirect` | `fastapi.applications` | `swagger_ui_redirect` | stable | public-dev-only | development-docs |  |  |  | FastAPI docs disabled by app config in production |
| `GET` | `/openapi.json` | `fastapi.applications` | `openapi` | stable | public-dev-only | development-docs |  |  |  | FastAPI docs disabled by app config in production |
| `GET` | `/redoc` | `fastapi.applications` | `redoc_html` | stable | public-dev-only | development-docs |  |  |  | FastAPI docs disabled by app config in production |
