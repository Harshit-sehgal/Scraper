/* DataForge frontend API contract helpers.
   Keep endpoint paths centralized so UI work does not drift from the
   documented frontend/backend contract. */

export const endpoints = {
  health: "/api/health",
  ready: "/api/ready",
  rootManifest: "/",
  systemStatus: "/api/system/status",

  jobs: "/api/jobs",
  job: (id) => `/api/jobs/${encodeURIComponent(id)}`,
  cancelJob: (id) => `/api/jobs/${encodeURIComponent(id)}/cancel`,
  deleteJob: (id) => `/api/jobs/${encodeURIComponent(id)}`,
  cleanupTerminalJobs: (keepRecent) => `/api/jobs/cleanup/terminal?keep_recent=${encodeURIComponent(keepRecent)}`,
  recleanJob: (id) => `/api/jobs/${encodeURIComponent(id)}/reclean`,
  exportCsv: (id) => `/api/jobs/${encodeURIComponent(id)}/export/csv`,
  exportJson: (id) => `/api/jobs/${encodeURIComponent(id)}/export/json`,
  exportExcel: (id) => `/api/jobs/${encodeURIComponent(id)}/export/excel`,

  discover: "/api/discover",
  schemaSuggest: "/api/schema/suggest",
  urlAnalyze: "/api/url/analyze",
  workflowDraftFromUrlAnalysis: "/api/workflow-drafts/from-url-analysis",

  authProfiles: "/api/auth-profiles",
  authProfilesQuery: (query) => `/api/auth-profiles?${query}`,
  startAuthProfileLogin: (id) => `/api/auth-profiles/${encodeURIComponent(id)}/start-login`,
  revokeAuthProfile: (id) => `/api/auth-profiles/${encodeURIComponent(id)}/revoke`,
  validateAuthProfile: (id) => `/api/auth-profiles/${encodeURIComponent(id)}/validate`,

  recycleBin: "/api/recycle_bin",
  recycleBinQuery: (query) => `/api/recycle_bin?${query}`,
  restoreRecycleItem: (id) => `/api/recycle_bin/${encodeURIComponent(id)}/restore`,
  deleteRecycleItem: (id) => `/api/recycle_bin/${encodeURIComponent(id)}`,

  workflows: "/api/workflows",
  workflow: (id) => `/api/workflows/${encodeURIComponent(id)}`,
  workflowRuns: (id, limit = 50) => `/api/workflows/${encodeURIComponent(id)}/runs?limit=${encodeURIComponent(limit)}`,
  runWorkflow: (id) => `/api/workflows/${encodeURIComponent(id)}/run`,

  billingPlan: "/api/saas/plan",
  billingSubscriptions: "/api/billing/subscriptions",
  billingCheckout: "/api/billing/checkout",
  aupStatus: "/api/saas/aup/status",
  aupAccept: "/api/saas/aup/accept",
  auditLog: (query) => `/api/system/audit-log?${query}`,
  auditLogLimit: (limit) => `/api/system/audit-log?limit=${encodeURIComponent(limit)}`,
  deleteUserData: "/api/user/data",

  operatorMode: "/api/operator/mode",
  operatorDashboard: "/api/operator/dashboard",
  operatorHealth: "/api/operator/health",
  operatorPredictions: "/api/operator/predictions",
  rateLimitStats: "/api/system/rate-limit-stats",
  topology: "/api/system/topology",

  /* SaaS identity features */
  emailVerificationStatus: "/api/saas/email-verification/status",
  emailVerificationSend: "/api/saas/email-verification/send",
  emailVerificationVerify: "/api/saas/email-verification/verify",
  passwordResetRequest: "/api/saas/password-reset/request",
  passwordResetConfirm: "/api/saas/password-reset/reset",
  invitationsPending: "/api/saas/invitations/pending",
  invitationRespond: (id) => `/api/saas/invitations/${encodeURIComponent(id)}/respond`,
  organizations: "/api/saas/orgs",
  organizationInvitations: (orgId, query) =>
    `/api/saas/orgs/${encodeURIComponent(orgId)}/invitations${query ? `?${query}` : ""}`,
  createOrganizationInvitation: (orgId) => `/api/saas/orgs/${encodeURIComponent(orgId)}/invitations`,
};

export const endpointGroups = {
  mvpRequired: [
    "health",
    "ready",
    "systemStatus",
    "jobs",
    "job",
    "cancelJob",
    "deleteJob",
    "exportCsv",
    "exportJson",
    "exportExcel",
    "discover",
    "schemaSuggest",
    "urlAnalyze",
  ],
  advancedLater: [
    "authProfiles",
    "recycleBin",
    "workflows",
    "billingPlan",
    "billingSubscriptions",
    "billingCheckout",
    "aupStatus",
    "aupAccept",
    "auditLog",
    "deleteUserData",
    "operatorMode",
    "operatorDashboard",
    "operatorHealth",
    "operatorPredictions",
    "rateLimitStats",
    "topology",
  ],
  stalePossiblyRemovable: ["workflowDraftFromUrlAnalysis", "recleanJob"],
};

export function normalizeApiPath(input) {
  const raw = String(input || "");
  if (!raw) return "";
  try {
    const base =
      typeof window !== "undefined" && window.location && window.location.origin
        ? window.location.origin
        : "http://127.0.0.1";
    const parsed = new URL(raw, base);
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return raw;
  }
}
