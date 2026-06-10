# Security Headers Documentation

## Overview

DataForge implements security headers to protect against common web vulnerabilities.

## Implemented Headers

### Content-Security-Policy (CSP)

**Purpose:** Prevents XSS, code injection, and data exfiltration.

**Configuration:**
```
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' data:;
font-src 'self';
connect-src 'self';
frame-ancestors 'none';
base-uri 'self';
form-action 'self';
```

**Testing:**
```bash
# Check CSP header
curl -I http://localhost:8000/ | grep -i content-security-policy
```

### X-Content-Type-Options

**Purpose:** Prevents MIME type sniffing.

**Value:** `nosniff`

**Testing:**
```bash
curl -I http://localhost:8000/ | grep -i x-content-type-options
```

### X-Frame-Options

**Purpose:** Prevents clickjacking.

**Value:** `DENY` or `SAMEORIGIN`

**Testing:**
```bash
curl -I http://localhost:8000/ | grep -i x-frame-options
```

### Strict-Transport-Security (HSTS)

**Purpose:** Enforces HTTPS connections.

**Value:** `max-age=31536000; includeSubDomains`

**Note:** Only applied when `DATAFORGE_ENV=production`

**Testing:**
```bash
curl -I https://your-domain/ | grep -i strict-transport-security
```

### X-XSS-Protection

**Purpose:** Enables browser XSS filtering (legacy).

**Value:** `1; mode=block`

**Testing:**
```bash
curl -I http://localhost:8000/ | grep -i x-xss-protection
```

### Referrer-Policy

**Purpose:** Controls referrer information.

**Value:** `strict-origin-when-cross-origin`

**Testing:**
```bash
curl -I http://localhost:8000/ | grep -i referrer-policy
```

### Permissions-Policy

**Purpose:** Controls browser features.

**Value:** `camera=(), microphone=(), geolocation=()`

**Testing:**
```bash
curl -I http://localhost:8000/ | grep -i permissions-policy
```

## Configuration

### Development

In development mode, security headers are relaxed for easier debugging:
- CSP may allow `unsafe-inline` for debugging
- HSTS is disabled
- CORS is more permissive

### Production

In production mode (`DATAFORGE_ENV=production`):
- All security headers are enforced
- HSTS is enabled with long max-age
- CORS is restricted to configured origins

### Customization

Security headers can be customized via:
- `backend/app/middleware/security_headers.py`
- Environment variables for specific settings
- Docker Compose for production deployments

## Testing

### Manual Testing

```bash
# Check all security headers
curl -I http://localhost:8000/

# Test CSP with inline script (should be blocked)
curl -H "Content-Type: text/html" http://localhost:8000/ -d "<script>alert('xss')</script>"
```

### Automated Testing

```bash
# Run security header tests
pytest backend/tests/test_security.py::TestSecurityHeaders -v

# Run all security tests
pytest backend/tests/test_security.py -v
```

### Security Scanning

```bash
# Run bandit security scanner
bandit -r backend/app/

# Run npm audit for frontend
npm audit
```

## Best Practices

1. **Enable all headers** in production
2. **Test regularly** with security scanners
3. **Monitor CSP violations** via `/api/system/csp-violations`
4. **Update policies** as application evolves
5. **Document exceptions** for any relaxed policies
6. **Use HTTPS** in production to enable HSTS

## CSP Violation Reporting

DataForge includes a CSP violation endpoint:

```bash
# Report CSP violations
curl -X POST http://localhost:8000/api/system/csp-violations \
  -H "Content-Type: application/json" \
  -d '{"csp-report": {...}}'
```

Violations are logged and can be monitored for security issues.

## References

- [OWASP Security Headers](https://owasp.org/www-project-secure-headers/)
- [MDN Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [Mozilla Observatory](https://observatory.mozilla.org/)
