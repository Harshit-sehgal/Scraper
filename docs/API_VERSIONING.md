# API Versioning Policy

## Overview

DataForge uses a **stable/experimental split** to manage API changes without breaking existing clients.

## API Categories

### Stable API (Production)

Routes marked as **stable** are:
- Available in production deployments
- Subject to semantic versioning
- Breaking changes require major version bump
- Documented in `docs/API.md`

**Current stable routes:** 45

### Experimental API (Research)

Routes marked as **experimental** are:
- Only available when `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true`
- Not subject to versioning guarantees
- May change or be removed without notice
- Used for research and development

**Current experimental routes:** 80

## Versioning Strategy

### Current State

DataForge uses a **monolithic version** (v0.x) with API stability guarantees:
- **v0.x**: Pre-1.0 development
- **v1.0**: First stable release (planned)

### Future Versioning

When v1.0 is released:
1. **URL-based versioning**: `/api/v1/...`, `/api/v2/...`
2. **Header-based versioning**: `Accept: application/vnd.dataforge.v1+json`
3. **Deprecation policy**: 6 months notice for breaking changes

## Change Management

### Adding New Routes

1. **Mark as experimental** initially
2. **Stabilize** after 3 months of production use
3. **Update docs** when stabilizing

### Breaking Changes

1. **Announce** in changelog and docs
2. **Deprecate** old endpoint (return warnings in headers)
3. **Remove** after deprecation period (6 months minimum)
4. **Provide migration guide**

### Non-Breaking Changes

- Adding optional parameters
- Adding new response fields
- Adding new endpoints
- Changing default behavior (if backward compatible)

## Client Compatibility

### Response Headers

Every API response includes:
- `X-API-Version`: Current API version
- `X-API-Stability`: `stable` or `experimental`
- `X-Deprecation-Warning`: Present if endpoint is deprecated

### OpenAPI Schema

- Stable routes: `/openapi.json` (when enabled)
- All routes: `/docs` (Swagger UI, when enabled)

## Migration Guide

### From v0.x to v1.0

When v1.0 is released:
1. Update base URL to include `/v1/`
2. Update authentication headers
3. Update response parsing (new fields)
4. Test against staging environment

### Experimental to Stable

When experimental routes stabilize:
1. Remove `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true` requirement
2. Update client code to use stable endpoints
3. Remove experimental endpoint usage

## Monitoring

### Route Inventory

```bash
# Generate route inventory
make api-docs

# Check stable routes
cat docs/API_STABLE.md

# Check experimental routes
cat docs/API_EXPERIMENTAL.md

# Check differences
cat docs/API_EXPERIMENTAL_DIFF.md
```

### Validation

```bash
# Verify route inventory matches code
make api-docs-check

# Run route auth matrix
python3 scripts/route_auth_matrix.py
```

## Best Practices

1. **Start experimental** - New features begin in experimental
2. **Stabilize gradually** - Move to stable after production validation
3. **Document changes** - Update API.md for any route changes
4. **Communicate deprecations** - Use headers and changelog
5. **Provide migration paths** - Help clients upgrade smoothly
