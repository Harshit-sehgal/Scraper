# SSRF & Egress Hardening Guide

## Overview

Server-Side Request Forgery (SSRF) protection in DataForge operates at
**two layers**: application-level controls (code) and network-level
controls (infrastructure). Both are required for a defence-in-depth
posture.

Application-layer controls are baked into the codebase. Network-layer
controls must be configured by the operator based on the deployment
environment (Kubernetes, AWS, Docker Compose, etc.).

---

## Layer 1 — Application-level controls (implemented)

These controls are active in all deployments and do not require
operator configuration.

| Control | Location | What it does |
|---------|----------|-------------|
| URL scheme validation | `url_safety.py:validate_public_http_url()` | Rejects non-http(s) schemes |
| IP literal validation | `url_safety.py:is_safe_ip()` | Rejects loopback, private, link-local, multicast, reserved, and non-global IPs |
| Non-canonical IP detection | `url_safety.py:_normalize_ip_literal()` | Catches hex/octal/decimal IP literals that bypass `ipaddress.ip_address` |
| Port allowlist | `url_safety.py:_ALLOWED_HTTP_PORTS` | Restricts outbound HTTP to ports 80, 443, 8080, 8443 |
| Internal TLD rejection | `url_safety.py:validate_public_http_url()` | Blocks `.local`, `.internal`, `.lan`, `.corp` TLDs |
| Cloud metadata protection | `url_safety.py:validate_public_http_url()` | Explicitly blocks 169.254.169.254, metadata.google.internal, instance-data |
| Safe async transport | `url_safety.py:SafeAsyncNetworkBackend` | Resolves DNS via `loop.getaddrinfo`, validates every IP at TCP connect time |
| Safe sync transport | `url_safety.py:SafeNetworkBackend` | Same validation for sync paths |
| Public-API transport wrapper | `url_safety.py:_UrlValidatingAsyncTransport` | PRIMARY SSRF enforcement — validates IPs before inner transport (uses only public httpx APIs) |
| Private-injection transport | `url_safety.py:SafeAsyncHTTPTransport` | SECONDARY enforcement — swaps `_pool._network_backend` for defense-in-depth |
| Startup self-check | `url_safety.py:verify_ssrf_self_check()` | Confirms both layers are wired correctly at startup |
| Job-creation URL validation | `routers/jobs_write.py:create_job()` | Validates manual-mode URLs via `validate_public_http_url` before persisting |
| Discovery URL safety filter | `routers/jobs_write.py:discover()` | Filters discovered URLs through `validate_public_http_url` |

---

## Layer 2 — Network-level controls (operator must configure)

These controls prevent SSRF even if the application layer is bypassed
(e.g., through an undiscovered code path, compromised dependency, or
misconfiguration). They are **not** baked into the application and
**must** be applied by the operator.

> **Important:** The examples below block all egress by default and then
> selectively allow HTTP/HTTPS to the internet. The scraper also needs
> egress to **internal services** (Postgres on port 5432, Redis if used
> as a queue backend, Prometheus scraping targets) **within the same VPC,
> Kubernetes namespace, or Docker network**. Add explicit allow rules
> for those destinations based on your deployment topology. The internal
> ``dataforge-net`` bridge in Docker Compose is already isolated from the
> host network; in Kubernetes you must add a separate ``to:`` clause for
> the Postgres pod or service.

### 2.1 Default-deny egress rules

Configure the container runtime or orchestration platform to deny all
egress traffic **except** to explicitly allowed destinations.

**Kubernetes NetworkPolicy** (`k8s/network-policies/egress.yaml`):

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: dataforge-default-deny-egress
  namespace: dataforge
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/part-of: dataforge
  policyTypes:
    - Egress
  egress:
    # Allow DNS (required for all pods)
    - ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
    # Allow outbound HTTPS to target scrape sites
    - ports:
        - port: 443
          protocol: TCP
        - port: 80
          protocol: TCP
      to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
              - 100.64.0.0/10
              - 198.18.0.0/15
    # Allow communication within the dataforge namespace
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: dataforge
```

**AWS Security Group** (Terraform example):

```hcl
resource "aws_security_group" "dataforge_egress" {
  name        = "dataforge-egress"
  description = "Egress rules for DataForge scraper"
  vpc_id      = var.vpc_id

  # HTTPS to internet (for scraping)
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS scraping"
  }

  # HTTP to internet (for scraping)
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP scraping"
  }

  # DNS
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "DNS"
  }

  # No other egress is permitted
}
```

### 2.2 Container runtime seccomp / AppArmor

**seccomp** (recommended for all deployments):

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {
      "names": [
        "accept", "bind", "connect", "listen", "getsockname",
        "getsockopt", "setsockopt", "socket", "read", "write",
        "open", "openat", "close", "fstat", "stat", "lseek",
        "mmap", "mprotect", "munmap", "brk", "sched_yield",
        "clone", "exit", "exit_group", "nanosleep", "clock_nanosleep"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

### 2.3 Outbound proxy (enterprise deployments)

Route all scraping traffic through an authenticated forward proxy so
egress can be logged, throttled, and audited independently of the
application:

```
scraper → forward-proxy (authenticated) → internet
```

Configure via `HTTP_PROXY` / `HTTPS_PROXY` env vars in the container:

```yaml
environment:
  - HTTP_PROXY=http://proxy.internal:3128
  - HTTPS_PROXY=http://proxy.internal:3128
  - NO_PROXY=localhost,127.0.0.1,postgres,nginx
```

### 2.4 Monitoring and alerting

Monitor for SSRF-related failures in application logs:

```
search: "SSRF" OR "unsafe IP" OR "restricted IP"
```

Prometheus alert (already defined in `prometheus_alerts.yml`):

```yaml
- alert: SSRFBlockedConnection
  expr: rate(dataforge_ssrf_rejects_total[5m]) > 0
  for: 1m
  labels:
    severity: warning
  annotations:
    summary: "SSRF connection blocked ({{ $value }} req/s)"
```

---

## 3. Testing egress hardening

### Unit tests (existing)

- `test_url_safety.py` — 20 tests covering IP validation, URL parsing,
  port allowlist, internal TLDs, cloud metadata, non-canonical IPs
- `test_egress_hardening.py` — 65 tests covering the safe transport
  layer (async + sync), DNS rebinding, UNIX socket rejection,
  public-API transport wrapper
- `test_ssrf_public_transport.py` — Tests the public-API transport
  wrapper specifically
- `test_production_hardening.py` — Integration tests for URL safety
  in the job creation flow

### Manual egress verification

To verify network-level controls are working:

```bash
# From inside the container, confirm you can reach scrape targets
python3 -c "
import httpx
# Should succeed
r = httpx.get('https://httpbin.org/ip', timeout=5)
print(f'Egress OK: {r.status_code}')
# Should fail (private IP)
try:
    r = httpx.get('http://10.0.0.1', timeout=5)
    print('ERROR: Private IP reachable!')
except Exception as e:
    print(f'Egress blocked private IP OK: {type(e).__name__}')
"
```

### Kubernetes egress test

```bash
kubectl run egress-test --image=curlimages/curl --rm -it --restart=Never -- \
  curl -s -o /dev/null -w '%{http_code}' https://httpbin.org/ip

kubectl run egress-test-blocked --image=curlimages/curl --rm -it --restart=Never -- \
  curl -s --connect-timeout 3 http://169.254.169.254/
# Expected: timeout or connection refused
```

---

## 4. Deployment checklist

- [ ] Application-layer SSR self-check passes at startup
      (`verify_ssrf_self_check()` returns `ok: True`)
- [ ] NetworkPolicy or security group denies all egress except
      HTTP(S) to internet + DNS + intra-cluster/internal
- [ ] Port allowlist active (non-80/443/8080/8443 outbound blocked)
- [ ] Container runs with `no-new-privileges: true`
- [ ] Container filesystem is `read_only: true` (except tmpfs)
- [ ] Production Compose has `security_opt` and `read_only` set
      (already applied in `docker-compose.prod.yml`)
- [ ] Cloud metadata endpoint blocked from container (169.254.169.254)
- [ ] Seccomp profile applied (if using Kubernetes)
- [ ] SSRF reject rate monitored (Prometheus alert active)
- [ ] Egress proxy configured for enterprise deployments
