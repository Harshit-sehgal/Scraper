"""Deployment validation checklist for staging environment."""

STAGING_VALIDATION_CHECKLIST = """
# DataForge Staging Deployment Validation

## Pre-Deployment
- [ ] Generate TLS certificates (self-signed for staging)
- [ ] Create .env.staging with real secrets (not placeholders)
- [ ] Verify backup storage is accessible
- [ ] Test restore procedure on backup file

## TLS & Secrets
- [ ] TLS certificate is valid (openssl x509 -in cert.pem -text)
- [ ] Private key matches certificate (openssl x509 -noout -modulus)
- [ ] CORS_ORIGINS does not contain wildcard '*'
- [ ] All API keys are different (user, operator, admin)
- [ ] Session secret is cryptographically random

## Deployment
- [ ] Docker image builds without warnings
- [ ] docker-compose.prod.yml starts without errors
- [ ] All containers reach healthy state within 2 min
- [ ] Logs show no FATAL or ERROR on startup

## Health Checks
- [ ] GET /health returns 200
- [ ] GET /ready returns 200
- [ ] GET /api/system/manifest returns server info
- [ ] GET /api/system/storage/status shows backend type

## Data Safety
- [ ] Create test job and verify data persists
- [ ] Trigger backup procedure
- [ ] Verify backup file exists and is > 1KB
- [ ] Restore from backup into new database
- [ ] Query restored data - matches original

## Monitoring
- [ ] Prometheus scrapes metrics (curl http://localhost:9090)
- [ ] AlertManager receives alert rule (curl http://localhost:9093)
- [ ] At least one metric is recorded (http_requests_total > 0)
- [ ] GET /api/system/retention/health returns monitoring data

## API Validation
- [ ] POST /api/jobs creates job (returns 201 with job_id)
- [ ] GET /api/jobs/{id} returns job details
- [ ] POST /api/billing/checkout returns approval_url
- [ ] GET /api/system/audit-log (admin only) returns events
- [ ] Rate limiter rejects after 600 req/min

## Rollback Procedure
- [ ] Note current git commit
- [ ] Deploy to v2 (a commit ahead)
- [ ] Verify v2 works
- [ ] Revert to original commit
- [ ] Verify rollback successful (no data loss)
- [ ] Test restore from backup during rollback

## Load Test (Optional)
- [ ] Create 10 jobs concurrently
- [ ] Verify all complete successfully
- [ ] Check error rate stays < 1%
- [ ] Verify browser pool doesn't exhaust

## Sign-Off
- [ ] All checks passed
- [ ] No warnings in logs
- [ ] Backup/restore works
- [ ] Rollback procedure works
- [ ] Ready for beta deployment ✅
"""

if __name__ == "__main__":
    print(STAGING_VALIDATION_CHECKLIST)

    # Write to file
    with open("/tmp/STAGING_VALIDATION_CHECKLIST.md", "w") as f:
        f.write(STAGING_VALIDATION_CHECKLIST)

    print("\n✅ Checklist saved to: /tmp/STAGING_VALIDATION_CHECKLIST.md")
