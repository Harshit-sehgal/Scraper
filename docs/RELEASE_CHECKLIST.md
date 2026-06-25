# DataForge Release Checklist

> Historical note:
> This document may contain older project status claims.
> For current verified status, see `docs/AGENT_TRUTH.md`.
>
> Verification warning:
> All-tests-pass, release, staging, and production claims in this file are not automatically trusted.
> Current readiness must be checked through `docs/AGENT_TRUTH.md` and the latest validation reports.

Use this checklist before every production release.

## Pre-Release Verification

- [ ] All tests pass: run `python3 scripts/validate_local.py --full` and record the current artifact path
- [ ] Frontend tests pass: `npm run test` (269+ passed)
- [ ] Lint clean: `ruff check backend/app/ backend/tests/`
- [ ] Format clean: `ruff format --check backend/app/ backend/tests/`
- [ ] Type check clean: `mypy backend/app/`
- [ ] Doctor passes: `make doctor` (12/12 required checks)
- [ ] API docs current: `make api-docs`

## Security Checks

- [ ] No hardcoded secrets: `bandit -r backend/app/ -q`
- [ ] No placeholder secrets in `.env.production`
- [ ] CORS origins match deployment domains
- [ ] API keys rotated since last release (if applicable)
- [ ] CSP policy reviewed and tightened

## Database Checks

- [ ] Migration scripts tested on staging
- [ ] Rollback script tested on staging
- [ ] Schema version documented in `docs/STATE_MODEL.md`

## Deployment Steps

1. **Tag the release**
   ```bash
   git tag -a v<VERSION> -m "Release v<VERSION>"
   git push origin v<VERSION>
   ```

2. **Build and push Docker image**
   ```bash
   DATAFORGE_IMAGE_TAG=v<VERSION> make build-prod
   docker tag dataforge:v<VERSION> registry.example.com/dataforge:v<VERSION>
   docker push registry.example.com/dataforge:v<VERSION>
   ```

3. **Deploy to staging**
   ```bash
   DATAFORGE_IMAGE_TAG=v<VERSION> docker compose -f docker-compose.prod.yml up -d --pull never
   ```

4. **Run smoke tests**
   ```bash
   make docker-smoke
   ```

5. **Verify health**
   ```bash
   curl -f https://staging.example.com/ready
   ```

6. **Deploy to production** (after staging verification)
   ```bash
   # Deploy the exact image tag verified in staging.
   DATAFORGE_IMAGE_TAG=v<VERSION> docker compose -f docker-compose.prod.yml up -d --pull never
   ```

## Post-Release Verification

- [ ] Health endpoint responds: `curl -f https://prod.example.com/ready`
- [ ] API key authentication works
- [ ] Session auth works (login/logout)
- [ ] Job creation works
- [ ] Job results export works
- [ ] No errors in logs for 15 minutes

## Rollback Procedure

If issues are detected:

1. **Stop the new deployment**
   ```bash
   docker compose -f docker-compose.prod.yml down
   ```

2. **Restore previous version**
   ```bash
   DATAFORGE_IMAGE_TAG=v<PREVIOUS_VERSION> docker compose -f docker-compose.prod.yml up -d --pull never
   ```

3. **Rollback database if needed**
   ```bash
   scripts/restore_postgres.sh <BACKUP_FILE>
   ```

4. **Verify rollback**
   ```bash
   curl -f https://prod.example.com/ready
   ```

5. **Notify team and create incident report**

## Version Numbering

- **Major** (X.0.0): Breaking API changes, data model changes
- **Minor** (0.X.0): New features, backward-compatible
- **Patch** (0.0.X): Bug fixes, security patches

## Changelog

Maintain a `CHANGELOG.md` with:
- Version number and date
- Added features
- Changed behavior
- Fixed bugs
- Security patches
- Breaking changes
