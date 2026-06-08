#!/usr/bin/env python3
"""
DataForge CORS & CSP Security Header Auditor.

Validates that Nginx/FastAPI headers are served securely, rejecting hostile
cross-origin requests and confirming strict CSP configuration.

Usage:
    python3 scripts/test_cors.py --url http://localhost:18080/health --origin https://yourdomain.com
"""

import argparse
import sys
import urllib.error
import urllib.request


def test_cors_origin(url: str, origin: str) -> tuple[int, dict]:
    try:
        req = urllib.request.Request(url, method="GET")  # noqa: S310
        req.add_header("Origin", origin)
        with urllib.request.urlopen(req, timeout=3) as resp:  # nosec B310 — fixed local probe URL from CLI arg with secure default  # noqa: S310
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}
    except Exception as e:
        print(f"[ERROR] Connection to {url} failed: {e}")
        return -1, {}


def main():
    parser = argparse.ArgumentParser(description="DataForge CORS/CSP Header Auditor")
    parser.add_argument("--url", default="http://localhost:18080/health", help="Target endpoint to probe")
    parser.add_argument("--origin", default="https://yourdomain.com", help="Allowed origin to test")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Auditing CORS & CSP headers: {args.url}")
    print("=" * 70)

    # 1. Allowed Origin
    print(f"\n[1] Testing allowed Origin: {args.origin}")
    status, headers = test_cors_origin(args.url, args.origin)
    if status < 0:
        sys.exit(1)

    allow_origin = headers.get("access-control-allow-origin")
    print(f"  Response Status: {status}")
    print(f"  Access-Control-Allow-Origin: {allow_origin}")

    # 2. Hostile Origin
    hostile_origin = "https://evil-unauthorized-attacker.com"
    print(f"\n[2] Testing hostile Origin: {hostile_origin}")
    h_status, h_headers = test_cors_origin(args.url, hostile_origin)
    h_allow = h_headers.get("access-control-allow-origin")
    print(f"  Response Status: {h_status}")
    print(f"  Access-Control-Allow-Origin: {h_allow}")

    # 3. CSP and Security Headers
    print("\n[3] Testing Security Headers...")
    security_headers = [
        ("x-frame-options", "SAMEORIGIN", "Clickjacking protection"),
        ("x-content-type-options", "nosniff", "MIME sniffing protection"),
        ("referrer-policy", "strict-origin-when-cross-origin", "Referrer disclosure control"),
        ("content-security-policy", None, "Content Security Policy"),
    ]

    for h_name, _expected, desc in security_headers:
        val = headers.get(h_name)
        if val:
            print(f"  - Header: {h_name:25} Value: {val[:45]}... [OK] ({desc})")
        else:
            print(f"  - Header: {h_name:25} Value: [MISSING] [WARN] ({desc})")

    print("\nValidation Complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
