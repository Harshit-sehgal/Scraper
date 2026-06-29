"""Comp 16: AUP enforcement — test acceptable use policy enforcement."""
from __future__ import annotations

from typing import Any

AUP_VERSION = "2026-06-v1"
AUP_RULES = {
    "max_requests_per_domain_per_hour": 1000,
    "max_records_per_job": 50000,
    "prohibited_content_types": ["adult", "hate_speech", "personal_data_scale"],
    "requires_robots_txt": True,
    "requires_attribution": True,
}


def _check_aup_compliance(
    domain: str,
    estimated_requests: int,
    content_type: str = "general",
    robots_respected: bool = True,
) -> dict[str, Any]:
    """Check if a job complies with the Acceptable Use Policy."""
    violations = []

    if estimated_requests > AUP_RULES["max_requests_per_domain_per_hour"]:
        violations.append(f"Estimated requests ({estimated_requests}) exceeds per-domain limit ({AUP_RULES['max_requests_per_domain_per_hour']})")

    if content_type in AUP_RULES["prohibited_content_types"]:
        violations.append(f"Content type '{content_type}' is prohibited by AUP")

    if AUP_RULES["requires_robots_txt"] and not robots_respected:
        violations.append("robots.txt must be respected per AUP")

    return {
        "compliant": len(violations) == 0,
        "aup_version": AUP_VERSION,
        "domain": domain,
        "violations": violations,
        "violation_count": len(violations),
    }


class TestAUPBasicCompliance:
    def test_normal_job_is_compliant(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=100)
        assert result["compliant"] is True
        assert result["violations"] == []

    def test_excessive_requests_violates(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=2000)
        assert result["compliant"] is False
        assert len(result["violations"]) == 1

    def test_prohibited_content_type_violates(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=10, content_type="adult")
        assert result["compliant"] is False
        assert "prohibited" in result["violations"][0].lower()


class TestAUPRobotsTxt:
    def test_robots_not_respected_violates(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=10, robots_respected=False)
        assert result["compliant"] is False

    def test_robots_respected_is_ok(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=10, robots_respected=True)
        assert result["compliant"] is True


class TestAUPVersioning:
    def test_aup_version_reported(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=10)
        assert result["aup_version"] == AUP_VERSION

    def test_violations_empty_when_compliant(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=10)
        assert result["violation_count"] == 0

    def test_multiple_violations(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=2000, content_type="adult", robots_respected=False)
        assert result["violation_count"] == 3
        assert result["compliant"] is False


class TestAUPPersonalData:
    def test_personal_data_scale_prohibited(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=10, content_type="personal_data_scale")
        assert result["compliant"] is False
        assert "personal_data_scale" in result["violations"][0]

    def test_general_content_allowed(self) -> None:
        result = _check_aup_compliance("example.com", estimated_requests=50, content_type="general")
        assert result["compliant"] is True
