"""Versioned legal page content for DataForge (E2.5).

Content is structured as ``(section_heading, [paragraphs])`` lists so the
router renders plain, dependency-free HTML. These are engineering-legal
baseline documents; professional legal review is the owner's task and
must bump the version constants when it changes them.
"""

from __future__ import annotations

from typing import Any

from app.saas import CURRENT_AUP_VERSION

TERMS_VERSION = "2026-08-18-v1"
PRIVACY_VERSION = "2026-08-18-v1"
AUP_VERSION = CURRENT_AUP_VERSION

_SERVICE_NAME = "DataForge"

TERMS_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. The Service",
        [
            f"{_SERVICE_NAME} provides automated web-extraction tooling for public, accessible web pages that the operator is lawfully entitled to process.",
            "You may use the Service only for content you are authorized to access, collect, and store.",
        ],
    ),
    (
        "2. Your Account",
        [
            "You are responsible for safeguarding your API keys and account credentials, and for all activity performed under them.",
            "You must provide accurate registration information and keep it current.",
        ],
    ),
    (
        "3. Acceptable Use",
        [
            "You must comply with the Acceptable Use Policy (AUP) that is part of these terms and is displayed at /legal/aup.",
            "Our Privacy Policy (at /legal/privacy) explains how we handle personal data; the data you extract is governed by your own legal obligations.",
            "Prohibited uses include bypassing access controls or anti-bot measures, circumventing paywalls, scraping private or unauthorized systems, and harvesting personal data without a lawful basis.",
        ],
    ),
    (
        "4. Fair Use and Limits",
        [
            "The Service enforces plan-based usage limits (fetches, jobs, exports). Exceeding a limit pauses the relevant activity until the plan is upgraded or usage is metered.",
            "You may not resell the Service or provide access to it to third parties without written permission.",
        ],
    ),
    (
        "5. Content You Extract",
        [
            "You retain responsibility for the lawfulness of content you extract, store, and redistribute.",
            f"{_SERVICE_NAME} does not claim ownership of content you process, but you grant us the right to process it to provide the Service.",
        ],
    ),
    (
        "6. Termination",
        [
            "You may stop using the Service at any time and delete your extracted data through the provided retention and deletion features.",
            "We may suspend access for material breaches of these terms or the AUP, with notice where practical.",
        ],
    ),
    (
        "7. Disclaimers",
        [
            'The Service is provided "as is" without warranties of any kind, including fitness for a particular purpose or uninterrupted availability.',
            "Automated extraction may produce incomplete or incorrect results; you are responsible for validating extracted data before relying on it.",
        ],
    ),
    (
        "8. Limitation of Liability",
        [
            "To the maximum extent permitted by law, DataForge is not liable for indirect, incidental, or consequential damages arising from use of the Service.",
            "This section survives termination of these terms.",
        ],
    ),
    (
        "9. Changes to These Terms",
        [
            "We may update these terms as the Service evolves; material changes are reflected by the version below and are effective on the published date.",
            "Continued use of the Service after a change constitutes acceptance.",
        ],
    ),
    (
        "10. Contact",
        [
            "Questions about these terms may be directed to the operator contact published with the Service.",
        ],
    ),
]

PRIVACY_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Data We Process",
        [
            f"{_SERVICE_NAME} processes account information (email, name), authentication data, usage metering data (fetches, jobs, exports), audit events, and the content you instruct the Service to extract.",
            "We do not process payment card data directly; payments are handled by our payment provider (Dodo Payments) under its own privacy terms.",
        ],
    ),
    (
        "2. Purpose and Legal Basis",
        [
            "Account and usage data are processed to provide, meter, and secure the Service (contract performance and legitimate interest).",
            "Extraction content is processed solely on your instruction and for the purposes you direct.",
        ],
    ),
    (
        "3. Retention",
        [
            "Extracted content and audit events are retained for the retention windows described in the Service settings and compliance documentation.",
            "You can delete your data, projects, jobs, and exports through the provided features at any time.",
        ],
    ),
    (
        "4. GDPR Rights",
        [
            "If GDPR applies to you, you may exercise rights of access, rectification, erasure, restriction, portability, and objection through the Service's data-request and deletion endpoints.",
            "The Service provides GDPR erasure tooling; requests are processed within the legally required timeframe.",
        ],
    ),
    (
        "5. Sharing",
        [
            "We do not sell personal data. Data is shared only with processors required to operate the Service (hosting, payments, notifications) under appropriate agreements.",
            "We may disclose data where lawfully required by authorities, to the extent permitted by law.",
        ],
    ),
    (
        "6. Security",
        [
            "We apply encryption at rest and in transit, centralized authentication, tenant isolation, and audit logging to protect data.",
            "No security measure is absolute; you are responsible for your credentials and for data you export.",
        ],
    ),
    (
        "7. Children",
        [
            "The Service is not directed at children under 13 (or the applicable age of consent); we do not knowingly collect their data.",
        ],
    ),
    (
        "8. Changes to This Policy",
        [
            f"Changes are published with a new version (currently {PRIVACY_VERSION}). Material changes are effective on the published date.",
        ],
    ),
]

AUP_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Purpose",
        [
            "This Acceptable Use Policy defines what the Service may and may not be used for. By using the Service you agree to it; the version you accepted is recorded with your account.",
        ],
    ),
    (
        "2. Lawful and Authorized Use Only",
        [
            "You may only use the Service to extract content you are lawfully entitled to access and process.",
            "You must respect the target site's terms, robots directives, and applicable laws, and you must identify the Service's requests as automated where required.",
        ],
    ),
    (
        "3. Prohibited Use",
        [
            "You may not use the Service to bypass CAPTCHAs, anti-bot defenses, paywalls, login walls, or access controls of any kind.",
            "You may not use the Service to scrape private, internal, or unauthorized systems, or to harvest personal data without a lawful basis.",
            "You may not use the Service for credential stuffing, session brute-forcing, or any unauthorized access technique.",
        ],
    ),
    (
        "4. Data Handling",
        [
            "You must comply with applicable data-protection law for any personal data you extract, including lawful basis, notice, and erasure obligations.",
            "You must not upload or extract malicious content, malware, or material that violates third-party rights.",
        ],
    ),
    (
        "5. Volume and Fair Use",
        [
            "The Service meters usage per plan. Intentionally excessive or disruptive load is prohibited; the Service may rate-limit or suspend activity that materially degrades it for others.",
        ],
    ),
    (
        "6. Monitoring and Enforcement",
        [
            "The Service logs audit events and metering data to operate, secure, and meter the Service.",
            "We may suspend access for violations of this policy, with notice where practical, and we cooperate with lawful enforcement requests.",
        ],
    ),
    (
        "7. Reporting",
        [
            "If you believe the Service is being used to harm you or your systems, contact the operator with evidence; we investigate reports in good faith.",
        ],
    ),
    (
        "8. Changes",
        [
            f"This policy is versioned (currently {AUP_VERSION}). Re-acceptance is required when the enforced version changes.",
        ],
    ),
]


def _sections_to_html(title: str, version: str, effective: str, sections: list[tuple[str, list[str]]]) -> str:
    body_parts: list[str] = []
    for heading, paragraphs in sections:
        body_parts.append(f"<h2>{heading}</h2>")
        for paragraph in paragraphs:
            body_parts.append(f"<p>{paragraph}</p>")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'" />
<title>{title} — {_SERVICE_NAME}</title>
<style>
body {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; margin: 0; background: #fff; color: #111; line-height: 1.6; }}
main {{ max-width: 720px; margin: 0 auto; padding: 48px 24px 96px; }}
h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
h2 {{ font-size: 1.05rem; margin-top: 2rem; }}
p {{ margin: 0.5rem 0; }}
.meta {{ color: #555; font-size: 0.85rem; border-bottom: 1px solid #ddd; padding-bottom: 1rem; margin-bottom: 1rem; }}
a {{ color: #111; }}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
<div class="meta">Version {version} &middot; Effective {effective} &middot; {_SERVICE_NAME}</div>
{"".join(body_parts)}
<p><a href="/">Back to DataForge</a></p>
</main>
</body>
</html>
"""


def build_page(slug: str) -> str:
    """Render a legal page's HTML for the given slug (terms/privacy/aup)."""
    if slug == "terms":
        return _sections_to_html("Terms of Service", TERMS_VERSION, "2026-08-18", TERMS_SECTIONS)
    if slug == "privacy":
        return _sections_to_html("Privacy Policy", PRIVACY_VERSION, "2026-08-18", PRIVACY_SECTIONS)
    if slug == "aup":
        return _sections_to_html("Acceptable Use Policy", AUP_VERSION, "2026-08-18", AUP_SECTIONS)
    msg = f"unknown legal page: {slug!r}"
    raise KeyError(msg)


LEGAL_PAGES: dict[str, Any] = {
    "terms": {"version": TERMS_VERSION, "effective": "2026-08-18"},
    "privacy": {"version": PRIVACY_VERSION, "effective": "2026-08-18"},
    "aup": {"version": AUP_VERSION, "effective": "2026-08-18"},
}
