# Route Inventory

**Generated from the registered FastAPI app. Do not edit generated rows by hand.**

**Generated:** 2026-07-03 23:14:20 UTC
**Command:** `python3 scripts/generate_route_inventory.py`

This inventory distinguishes stable API routes, experimental API routes,
development docs/static routes, health/readiness routes, and session/auth routes.

**Total route rows:** 199

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
| `POST` | `/api/billing/checkout` | `app.billing.checkout` | `create_checkout` | stable | protected | operator-or-admin | require_role |  | CheckoutResponse | route dependency accepts admin/operator |
| `GET` | `/api/billing/stub-return/{plan_tier}/{request_id}` | `app.billing.checkout` | `stub_return` | stable | protected | authenticated-user |  |  |  | protected by global /api middleware; no route-level role dependency |
| `GET` | `/api/billing/subscriptions` | `app.billing.webhooks` | `list_subscriptions` | stable | protected | operator-or-admin | require_principal, require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/billing/subscriptions/{customer_id}` | `app.billing.webhooks` | `get_subscription` | stable | protected | operator-or-admin | require_principal, require_role |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/billing/webhook` | `app.billing.webhooks` | `billing_webhook` | stable | protected | authenticated-user |  |  | dict | protected by global /api middleware; no route-level role dependency; mutation role should be reviewed |
| `POST` | `/api/compliance/gdpr/forget` | `app.routers.user_data` | `gdpr_forget` | stable | protected | authenticated-user | require_principal |  | DeleteMyDataResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/discover` | `app.routers.jobs_write` | `discover` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/discover/sitemap` | `app.routers.jobs_write` | `discover_sitemap` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/download/{filename}` | `app.routers.exports` | `serve_binary_download` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `POST` | `/api/exports/batch` | `app.routers.exports` | `batch_export` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/jobs` | `app.routers.jobs_read` | `list_jobs` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs` | `app.routers.jobs_write` | `create_job` | stable | protected | operator-or-admin | require_plan_limit.<locals>.dependency, require_role |  | JobCreateResponse | route dependency accepts admin/operator |
| `POST` | `/api/jobs/batch` | `app.routers.jobs_write` | `batch_submit` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/jobs/cleanup/terminal` | `app.routers.jobs_write` | `clear_terminal_jobs` | stable | protected | admin | require_role |  | ClearTerminalResponse | require_role/admin-only dependency |
| `DELETE` | `/api/jobs/{job_id}` | `app.routers.jobs_write` | `delete_job` | stable | protected | admin | require_role |  | dict | require_role/admin-only dependency |
| `GET` | `/api/jobs/{job_id}` | `app.routers.jobs_read` | `get_job` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs/{job_id}/cancel` | `app.routers.jobs_write` | `cancel_job` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/cascade-trace` | `app.routers.jobs_read` | `get_job_cascade_trace` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs/{job_id}/clone` | `app.routers.jobs_write` | `clone_job` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/debug` | `app.routers.jobs_read` | `debug_job` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `GET` | `/api/jobs/{job_id}/diff` | `app.routers.jobs_read` | `get_job_diff` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs/{job_id}/email` | `app.routers.jobs_write` | `email_job_results` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/events` | `app.routers.jobs_read` | `get_job_events` | stable | protected | authenticated-user | require_principal |  | JobEventsResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/jobs/{job_id}/export/csv` | `app.routers.exports` | `export_csv` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `GET` | `/api/jobs/{job_id}/export/excel` | `app.routers.exports` | `export_excel` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `GET` | `/api/jobs/{job_id}/export/json` | `app.routers.exports` | `export_json` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `PATCH` | `/api/jobs/{job_id}/extraction` | `app.routers.jobs_write` | `update_job_extraction` | stable | protected | operator-or-admin | require_principal |  | JobExtractionUpdateResponse | route dependency accepts admin/operator |
| `PATCH` | `/api/jobs/{job_id}/fetch-strategy` | `app.routers.jobs_write` | `update_fetch_strategy_literal` | stable | protected | operator-or-admin | require_principal |  | StatusResponse | route dependency accepts admin/operator |
| `PATCH` | `/api/jobs/{job_id}/headers` | `app.routers.jobs_write` | `update_job_headers` | stable | protected | operator-or-admin | require_principal |  | StatusResponse | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/network-log` | `app.routers.jobs_read` | `get_job_network_log` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `GET` | `/api/jobs/{job_id}/notification-channels` | `app.routers.jobs_write` | `list_notification_channels` | stable | protected | operator-or-admin | require_principal |  | list | route dependency accepts admin/operator |
| `POST` | `/api/jobs/{job_id}/notification-channels` | `app.routers.jobs_write` | `create_notification_channel` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/jobs/{job_id}/notification-channels/{channel_id}` | `app.routers.jobs_write` | `delete_notification_channel` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `PATCH` | `/api/jobs/{job_id}/notification-channels/{channel_id}` | `app.routers.jobs_write` | `update_notification_channel` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/quality` | `app.routers.jobs_read` | `get_job_quality` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `GET` | `/api/jobs/{job_id}/quality/trends` | `app.routers.jobs_read` | `get_job_quality_trends` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `POST` | `/api/jobs/{job_id}/reclean` | `app.routers.jobs_write` | `reclean_job` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/jobs/{job_id}/results` | `app.routers.jobs_write` | `delete_job_results` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/results` | `app.routers.jobs_read` | `get_job_results` | stable | protected | authenticated-user | require_principal |  | JobResultsResponse | route dependency accepts admin/operator/user |
| `PATCH` | `/api/jobs/{job_id}/results/{record_id}` | `app.routers.jobs_write` | `correct_record` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/screenshot` | `app.routers.jobs_read` | `get_job_screenshot` | stable | protected | authenticated-user | require_principal |  |  | route dependency accepts admin/operator/user |
| `PATCH` | `/api/jobs/{job_id}/strategy` | `app.routers.jobs_write` | `update_job_strategy` | stable | protected | operator-or-admin | require_principal |  | StatusResponse | route dependency accepts admin/operator |
| `GET` | `/api/jobs/{job_id}/structured-events` | `app.routers.jobs_read` | `get_job_structured_events` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `PATCH` | `/api/jobs/{job_id}/user-agent` | `app.routers.jobs_write` | `update_job_user_agent` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `PATCH` | `/api/jobs/{job_id}/wait-conditions` | `app.routers.jobs_write` | `update_job_wait_conditions` | stable | protected | operator-or-admin | require_principal |  | StatusResponse | route dependency accepts admin/operator |
| `PATCH` | `/api/jobs/{job_id}/webhook` | `app.routers.jobs_write` | `update_job_webhook` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `POST` | `/api/jobs/{job_id}/webhook/redeliver` | `app.routers.jobs_write` | `redeliver_job_webhook` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/operator/denylist` | `app.routers.operator` | `remove_denylist_entry` | stable | protected | admin | require_role_with_user |  | RemoveDenylistResponse | require_role/admin-only dependency |
| `GET` | `/api/operator/denylist` | `app.routers.operator` | `list_denylist` | stable | protected | operator-or-admin | require_role_with_user |  | list | route dependency accepts admin/operator |
| `POST` | `/api/operator/denylist` | `app.routers.operator` | `add_denylist_entry` | stable | protected | admin | require_role_with_user |  | DenylistEntryResponse | require_role/admin-only dependency |
| `DELETE` | `/api/recycle_bin` | `app.routers.jobs_write` | `clear_recycle_bin` | stable | protected | admin | require_role |  | dict | require_role/admin-only dependency |
| `GET` | `/api/recycle_bin` | `app.routers.jobs_read` | `list_recycle_bin` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `DELETE` | `/api/recycle_bin/{job_id}` | `app.routers.jobs_write` | `hard_delete_job` | stable | protected | admin | require_role |  | dict | require_role/admin-only dependency |
| `POST` | `/api/recycle_bin/{job_id}/restore` | `app.routers.jobs_write` | `restore_job` | stable | protected | admin | require_role |  | dict | require_role/admin-only dependency |
| `GET` | `/api/reviews` | `app.routers.jobs_write` | `list_reviews` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `GET` | `/api/reviews/{review_id}` | `app.routers.jobs_write` | `get_review` | stable | protected | authenticated-user | require_principal |  | dict | route dependency accepts admin/operator/user |
| `PATCH` | `/api/reviews/{review_id}` | `app.routers.jobs_write` | `update_review` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/saas/aup/accept` | `app.saas.routes.aup` | `accept_aup` | stable | protected | authenticated-user | require_role_with_user |  | AupStatusResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/aup/status` | `app.saas.routes.aup` | `get_aup_status` | stable | protected | authenticated-user | require_role_with_user |  | AupStatusResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/email-verification/send` | `app.saas.routes.profile` | `send_email_verification` | stable | protected | authenticated-user | require_role_with_user |  | EmailVerificationSendResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/email-verification/status` | `app.saas.routes.profile` | `email_verification_status` | stable | protected | authenticated-user | require_role_with_user |  | EmailVerificationStatusResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/email-verification/verify` | `app.saas.routes.profile` | `verify_email` | stable | protected | authenticated-user | require_role_with_user |  | EmailVerifyResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/invitations/pending` | `app.saas.routes.orgs` | `get_pending_invitations` | stable | protected | authenticated-user | require_role_with_user |  | list | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/invitations/{invitation_id}/respond` | `app.saas.routes.orgs` | `respond_to_invitation` | stable | protected | authenticated-user | require_role_with_user |  | InvitationRespondResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/me` | `app.saas.routes.profile` | `get_my_profile` | stable | protected | authenticated-user | require_role_with_user |  | UserProfileResponse | route dependency accepts admin/operator/user |
| `DELETE` | `/api/saas/memberships/{membership_id}` | `app.saas.routes.orgs` | `remove_member` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/saas/orgs` | `app.saas.routes.orgs` | `list_my_organizations` | stable | protected | authenticated-user | require_role_with_user |  | OrgListResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/orgs` | `app.saas.routes.orgs` | `create_organization` | stable | protected | operator-or-admin | require_role_with_user |  | OrgResponse | route dependency accepts admin/operator |
| `DELETE` | `/api/saas/orgs/{org_id}` | `app.saas.routes.orgs` | `delete_organization` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/saas/orgs/{org_id}` | `app.saas.routes.orgs` | `get_organization` | stable | protected | authenticated-user | require_principal |  | OrgResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/orgs/{org_id}/invitations` | `app.saas.routes.orgs` | `list_org_invitations` | stable | protected | operator-or-admin | require_principal |  | InvitationListResponse | route dependency accepts admin/operator |
| `POST` | `/api/saas/orgs/{org_id}/invitations` | `app.saas.routes.orgs` | `create_invitation` | stable | protected | operator-or-admin | require_principal |  | InvitationResponse | route dependency accepts admin/operator |
| `GET` | `/api/saas/orgs/{org_id}/members` | `app.saas.routes.orgs` | `list_org_members` | stable | protected | authenticated-user | require_principal |  | list | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/orgs/{org_id}/projects` | `app.saas.routes.projects` | `list_org_projects` | stable | protected | authenticated-user | require_principal |  | ProjectListResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/password-reset/request` | `app.saas.routes.signup` | `request_password_reset` | stable | protected | authenticated-user |  |  | PasswordResetResponse | protected by global /api middleware; no route-level role dependency; mutation role should be reviewed |
| `POST` | `/api/saas/password-reset/reset` | `app.saas.routes.signup` | `confirm_password_reset` | stable | protected | authenticated-user |  |  | PasswordResetConfirmResponse | protected by global /api middleware; no route-level role dependency; mutation role should be reviewed |
| `GET` | `/api/saas/plan` | `app.saas.router` | `get_plan_info` | stable | protected | authenticated-user | require_role_with_user |  | PlanInfoResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/projects` | `app.saas.routes.projects` | `create_project` | stable | protected | operator-or-admin | require_aup_accepted, require_role_with_user |  | ProjectResponse | route dependency accepts admin/operator |
| `DELETE` | `/api/saas/projects/{project_id}` | `app.saas.routes.projects` | `delete_project` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/saas/projects/{project_id}` | `app.saas.routes.projects` | `get_project` | stable | protected | authenticated-user | require_principal |  | ProjectResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/saas/projects/{project_id}/keys` | `app.saas.routes.projects` | `list_project_api_keys` | stable | protected | authenticated-user | require_role_with_user |  | ApiKeyListResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/saas/projects/{project_id}/keys` | `app.saas.routes.projects` | `create_api_key` | stable | protected | operator-or-admin | require_aup_accepted, require_role_with_user |  | ApiKeyCreateResponse | route dependency accepts admin/operator |
| `DELETE` | `/api/saas/projects/{project_id}/keys/{key_id}` | `app.saas.routes.projects` | `revoke_api_key` | stable | protected | operator-or-admin | require_role_with_user |  |  | route dependency accepts admin/operator |
| `GET` | `/api/saas/usage` | `app.saas.router` | `get_usage_summary` | stable | protected | authenticated-user | require_role_with_user |  | UsageSummaryResponse | route dependency accepts admin/operator/user |
| `GET` | `/api/scheduled` | `app.routers.scheduled_monitoring` | `list_scheduled_jobs` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/scheduled` | `app.routers.scheduled_monitoring` | `create_scheduled_job` | stable | protected | operator-or-admin | require_aup_accepted, require_principal |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/scheduled/{job_id}` | `app.routers.scheduled_monitoring` | `delete_scheduled_job` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/scheduled/{job_id}` | `app.routers.scheduled_monitoring` | `get_scheduled_job` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `PUT` | `/api/scheduled/{job_id}` | `app.routers.scheduled_monitoring` | `update_scheduled_job` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/scheduled/{job_id}/changes` | `app.routers.scheduled_monitoring` | `detect_changes` | stable | protected | operator-or-admin | require_principal |  | ScheduledJobChangesResponse | route dependency accepts admin/operator |
| `POST` | `/api/schema/suggest` | `app.routers.jobs_write` | `suggest_schema` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/scraper/browser` | `app.routers.scraper` | `get_browser_stats` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/scraper/config` | `app.routers.scraper` | `get_scraper_config` | stable | protected | operator-or-admin | require_role |  | ScraperConfigResponse | route dependency accepts admin/operator |
| `POST` | `/api/scraper/diagnostics` | `app.routers.scraper` | `get_scraper_diagnostics` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/scraper/health/legacy` | `app.routers.scraper` | `get_legacy_domain_health` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/scraper/memory/stats` | `app.routers.scraper` | `get_selector_memory_brief` | stable | protected | operator-or-admin | require_role |  | SelectorMemoryStatsResponse | route dependency accepts admin/operator |
| `POST` | `/api/scraper/preview` | `app.routers.scraper` | `preview_extraction` | stable | protected | operator-or-admin | require_role |  | PreviewResponse | route dependency accepts admin/operator |
| `GET` | `/api/scraper/regressions` | `app.routers.scraper` | `get_regression_archive` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/scraper/regressions/generate-all-tests` | `app.routers.scraper` | `generate_all_replay_tests` | stable | protected | admin | require_role |  | RegressionGenerateAllResponse | require_role/admin-only dependency |
| `GET` | `/api/scraper/regressions/{entry_id}` | `app.routers.scraper` | `get_regression_detail` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/scraper/regressions/{entry_id}/generate-test` | `app.routers.scraper` | `generate_regression_replay_test` | stable | protected | admin | require_role |  | RegressionTestGenerateResponse | require_role/admin-only dependency |
| `POST` | `/api/scraper/screenshot` | `app.routers.scraper` | `capture_screenshot` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/scraper/selectors/cleanup` | `app.routers.scraper` | `trigger_selector_cleanup` | stable | protected | admin | require_role |  | SelectorCleanupResponse | require_role/admin-only dependency |
| `GET` | `/api/scraper/selectors/domain/{domain}` | `app.routers.scraper` | `get_domain_selector_confidence` | stable | protected | operator-or-admin | require_role |  | DomainConfidenceResponse | route dependency accepts admin/operator |
| `GET` | `/api/scraper/selectors/low-confidence` | `app.routers.scraper` | `get_low_confidence_selectors` | stable | protected | operator-or-admin | require_role |  | LowConfidenceSelectorsResponse | route dependency accepts admin/operator |
| `GET` | `/api/scraper/selectors/stats` | `app.routers.scraper` | `get_selector_memory_stats` | stable | protected | operator-or-admin | require_role |  | SelectorMemoryFullStatsResponse | route dependency accepts admin/operator |
| `GET` | `/api/scraper/stats` | `app.routers.scraper` | `get_scraper_stats` | stable | protected | operator-or-admin | require_role |  | ScraperStatsResponse | route dependency accepts admin/operator |
| `DELETE` | `/api/scraper/telemetry` | `app.routers.scraper` | `clear_telemetry` | stable | protected | admin | require_role |  | StatusResponse | require_role/admin-only dependency |
| `GET` | `/api/scraper/telemetry` | `app.routers.scraper` | `get_recent_telemetry` | stable | protected | operator-or-admin | require_role |  | list | route dependency accepts admin/operator |
| `GET` | `/api/system/audit-log` | `app.routers.system` | `get_audit_log` | stable | protected | admin | require_role |  | AuditLogResponse | require_role/admin-only dependency |
| `POST` | `/api/system/csp-violations` | `app.routers.system` | `csp_violations` | stable | public |  |  |  |  | explicit API middleware exemption |
| `GET` | `/api/system/extraction-health` | `app.routers.system` | `extraction_health` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/system/extraction-rate` | `app.routers.system` | `extraction_rate` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/system/rate-limit-stats` | `app.routers.system` | `rate_limit_stats` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/system/status` | `app.routers.system` | `system_status` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/system/storage/status` | `app.routers.system` | `storage_status` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/templates` | `app.routers.jobs_write` | `list_templates` | stable | protected | operator-or-admin | require_principal |  | list | route dependency accepts admin/operator |
| `POST` | `/api/templates` | `app.routers.jobs_write` | `create_template` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/templates/{template_id}` | `app.routers.jobs_write` | `delete_template` | stable | protected | admin | require_principal |  |  | require_role/admin-only dependency |
| `GET` | `/api/templates/{template_id}` | `app.routers.jobs_write` | `get_template` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `PATCH` | `/api/templates/{template_id}` | `app.routers.jobs_write` | `update_template` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/url/analyze` | `app.routers.system` | `analyze_url` | stable | protected | operator-or-admin | require_role |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/usage/stats` | `app.routers.jobs_write` | `get_usage_stats` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/usage/stats/record` | `app.routers.jobs_write` | `record_usage` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/user/data` | `app.routers.user_data` | `delete_my_data` | stable | protected | authenticated-user | require_principal |  | DeleteMyDataResponse | route dependency accepts admin/operator/user |
| `POST` | `/api/workflow-drafts/from-url-analysis` | `app.routers.workflow` | `create_workflow_draft_from_url_analysis` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/workflow-drafts/{draft_id}/detect-fields` | `app.routers.workflow` | `detect_workflow_draft_fields` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/workflow-drafts/{draft_id}/manual-mapping` | `app.routers.workflow` | `create_workflow_from_manual_mapping` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/workflows` | `app.routers.workflow` | `list_workflows` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/workflows` | `app.routers.workflow` | `create_workflow` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `DELETE` | `/api/workflows/{workflow_id}` | `app.routers.workflow` | `delete_workflow` | stable | protected | operator-or-admin | require_principal |  |  | route dependency accepts admin/operator |
| `GET` | `/api/workflows/{workflow_id}` | `app.routers.workflow` | `get_workflow` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `PATCH` | `/api/workflows/{workflow_id}` | `app.routers.workflow` | `patch_workflow` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `PUT` | `/api/workflows/{workflow_id}` | `app.routers.workflow` | `update_workflow` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/workflows/{workflow_id}/preview` | `app.routers.workflow` | `preview_workflow` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/workflows/{workflow_id}/run` | `app.routers.workflow` | `run_workflow` | stable | protected | operator-or-admin | require_principal |  | WorkflowRunQueuedResponse | route dependency accepts admin/operator |
| `GET` | `/api/workflows/{workflow_id}/runs` | `app.routers.workflow` | `list_workflow_runs` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/workflows/{workflow_id}/runs/{run_id}` | `app.routers.workflow` | `get_workflow_run` | stable | protected | operator-or-admin | require_principal |  | dict | route dependency accepts admin/operator |

## Experimental Api Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/operator/dashboard` | `app.routers.experimental` | `get_system_dashboard` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/operator/health` | `app.routers.experimental` | `get_operator_health_summary` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/operator/mode` | `app.routers.experimental` | `get_current_mode` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `POST` | `/api/operator/mode` | `app.routers.experimental` | `set_operator_mode` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/operator/predictions` | `app.routers.experimental` | `get_degradation_predictions` | experimental | protected | authenticated-user | require_role, verify_experimental_enabled |  | dict | route dependency accepts admin/operator/user |
| `GET` | `/api/operator/predictions/{domain}` | `app.routers.experimental` | `get_domain_prediction` | experimental | protected | authenticated-user | require_role, verify_experimental_enabled |  | dict | route dependency accepts admin/operator/user |
| `GET` | `/api/scraper/economics` | `app.routers.experimental` | `get_extraction_economics` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/domain/{domain}` | `app.routers.experimental` | `get_domain_health` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/domains` | `app.routers.experimental` | `get_all_domains_health` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/scraper/health/summary` | `app.routers.experimental` | `get_system_health_summary` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `POST` | `/api/scraper/ml/learn` | `app.routers.experimental` | `record_selector_learning` | experimental | protected | operator-or-admin | require_role, verify_experimental_enabled |  | dict | route dependency accepts admin/operator |
| `POST` | `/api/scraper/ml/optimize/domain/{domain}` | `app.routers.experimental` | `optimize_domain_selectors` | experimental | protected | operator-or-admin | require_role, verify_experimental_enabled |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/scraper/ml/optimize/domain/{domain}/history` | `app.routers.experimental` | `get_optimization_history` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/scraper/strategy/domain/{domain}` | `app.routers.experimental` | `get_domain_strategy_analysis` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `POST` | `/api/scraper/strategy/evolve/{domain}` | `app.routers.experimental` | `evolve_domain_strategy` | experimental | protected | operator-or-admin | require_role, verify_experimental_enabled |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/scraper/strategy/recommend/{domain}` | `app.routers.experimental` | `recommend_fetch_strategy` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `POST` | `/api/scraper/strategy/record` | `app.routers.experimental` | `record_strategy_attempt` | experimental | protected | operator-or-admin | require_role, verify_experimental_enabled |  | dict | route dependency accepts admin/operator |
| `GET` | `/api/scraper/strategy/report` | `app.routers.experimental` | `get_all_strategies_report` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/scraper/trends` | `app.routers.experimental` | `get_extraction_trends` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/scraper/trends/{domain}` | `app.routers.experimental` | `get_domain_trend` | experimental | protected | authenticated-user | require_role, verify_experimental_enabled |  | dict | route dependency accepts admin/operator/user |
| `GET` | `/api/system/acquisition/telemetry` | `app.routers.experimental` | `acquisition_telemetry` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/agency` | `app.routers.experimental` | `system_agency` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/crystalline` | `app.routers.experimental` | `system_crystalline` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/domain-policy` | `app.routers.experimental` | `system_domain_policy` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/export/knowledge` | `app.routers.experimental` | `export_knowledge` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/history/topology` | `app.routers.experimental` | `system_topology_history` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `POST` | `/api/system/merge/knowledge` | `app.routers.experimental` | `merge_knowledge` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/observability` | `app.routers.experimental` | `system_observability` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `POST` | `/api/system/refactor/compress` | `app.routers.experimental` | `trigger_manifold_compression` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/replay/chain` | `app.routers.experimental` | `system_replay_chains` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/replay/events` | `app.routers.experimental` | `system_replay_events` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/replay/status` | `app.routers.experimental` | `system_replay_status` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `POST` | `/api/system/scheduler/step` | `app.routers.experimental` | `process_cognitive_tasks` | experimental | protected | admin | require_role, verify_experimental_enabled |  |  | require_role/admin-only dependency |
| `GET` | `/api/system/search` | `app.routers.experimental` | `system_search` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |
| `GET` | `/api/system/topology` | `app.routers.experimental` | `system_topology` | experimental | protected | admin | require_role, verify_experimental_enabled |  | dict | require_role/admin-only dependency |

## Session/Auth Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/api/saas/signup` | `app.saas.routes.signup` | `signup` | stable | public |  |  |  | SignupResponse | explicit API middleware exemption |
| `DELETE` | `/api/session` | `app.routers.session` | `destroy_session` | stable | public |  |  |  | SessionDestroyResponse | explicit API middleware exemption |
| `POST` | `/api/session` | `app.routers.session` | `create_session` | stable | public |  |  |  | SessionCreateResponse | explicit API middleware exemption |
| `GET` | `/api/session/me` | `app.routers.session` | `get_session` | stable | public |  |  |  | SessionMeResponse | explicit API middleware exemption |

## Health/Readiness Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/` | `app.routers.health` | `root` | stable | public |  |  |  | dict | non-API probe/static route |
| `MOUNT` | `/app` | `starlette.routing` | `Mount` | stable | public |  |  |  |  | mounted ASGI/static route |
| `GET` | `/health` | `app.routers.health` | `health` | stable | public |  |  |  | dict | non-API probe/static route |
| `GET` | `/metrics` | `app.routers.system` | `metrics` | stable | protected | metrics-token-if-configured |  |  |  | settings.METRICS_TOKEN check in endpoint |
| `GET` | `/ready` | `app.routers.health` | `ready` | stable | public |  |  |  | dict | non-API probe/static route |

## Docs/Openapi/Static/Dev Routes

| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `MOUNT` | `/dashboard` | `starlette.routing` | `Mount` | stable | public |  |  |  |  | mounted ASGI/static route |
| `GET` | `/docs` | `fastapi.applications` | `swagger_ui_html` | stable | public-dev-only | development-docs |  |  |  | FastAPI docs disabled by app config in production |
| `GET` | `/docs/oauth2-redirect` | `fastapi.applications` | `swagger_ui_redirect` | stable | public-dev-only | development-docs |  |  |  | FastAPI docs disabled by app config in production |
| `GET` | `/health/browser` | `app.routers.health` | `health_browser` | stable | public |  |  |  | dict | non-API route |
| `GET` | `/health/db` | `app.routers.health` | `health_db` | stable | public |  |  |  | dict | non-API route |
| `GET` | `/health/worker` | `app.routers.health` | `health_worker` | stable | public |  |  |  | dict | non-API route |
| `MOUNT` | `/landing` | `starlette.routing` | `Mount` | stable | public |  |  |  |  | mounted ASGI/static route |
| `GET` | `/openapi.json` | `fastapi.applications` | `openapi` | stable | public-dev-only | development-docs |  |  |  | FastAPI docs disabled by app config in production |
| `GET` | `/redoc` | `fastapi.applications` | `redoc_html` | stable | public-dev-only | development-docs |  |  |  | FastAPI docs disabled by app config in production |
