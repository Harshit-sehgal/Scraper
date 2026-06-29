from __future__ import annotations


def _score_ip_reputation(
    is_datacenter: bool = False,
    is_residential: bool = True,
    is_mobile: bool = False,
    is_vpn: bool = False,
    is_proxy: bool = False,
    is_tor: bool = False,
    asn_age_days: int = 3650,
    previous_blocks: int = 0,
    abuse_reports: int = 0,
) -> float:
    """Score IP reputation from 0.0 (bad) to 1.0 (good)."""
    score = 0.9
    if is_datacenter:
        score -= 0.15
    if is_vpn:
        score -= 0.25
    if is_proxy:
        score -= 0.20
    if is_tor:
        score -= 0.50
    if is_mobile:
        score += 0.10
    if is_residential:
        score += 0.10
    asn_factor = min(1.0, asn_age_days / 3650)
    score *= asn_factor
    block_penalty = min(0.3, previous_blocks * 0.05)
    score -= block_penalty
    abuse_penalty = min(0.4, abuse_reports * 0.02)
    score -= abuse_penalty
    return max(0.0, min(1.0, score))


def _classify_ip_quality(score: float) -> str:
    if score >= 0.7:
        return "good"
    if score >= 0.4:
        return "fair"
    return "poor"


class TestIPQualityScoring:
    """Anti 28: IP reputation scoring."""

    def test_residential_ip_scores_high(self) -> None:
        score = _score_ip_reputation(is_residential=True)
        assert score > 0.8

    def test_datacenter_ip_scores_lower(self) -> None:
        res = _score_ip_reputation(is_residential=True)
        dc = _score_ip_reputation(is_datacenter=True, is_residential=False)
        assert dc < res

    def test_tor_ip_scores_poor(self) -> None:
        score = _score_ip_reputation(is_tor=True, is_residential=False)
        assert score < 0.6

    def test_vpn_scores_lower_than_residential(self) -> None:
        vpn = _score_ip_reputation(is_vpn=True, is_residential=False)
        res = _score_ip_reputation(is_residential=True)
        assert vpn < res

    def test_proxy_scores_lower_than_residential(self) -> None:
        proxy = _score_ip_reputation(is_proxy=True, is_residential=False)
        res = _score_ip_reputation(is_residential=True)
        assert proxy < res

    def test_blocks_reduce_score(self) -> None:
        clean = _score_ip_reputation(is_residential=True)
        blocked = _score_ip_reputation(is_residential=True, previous_blocks=5)
        assert blocked < clean

    def test_abuse_reports_reduce_score(self) -> None:
        clean = _score_ip_reputation(is_residential=True)
        abused = _score_ip_reputation(is_residential=True, abuse_reports=10)
        assert abused < clean

    def test_young_asn_scores_lower(self) -> None:
        old = _score_ip_reputation(is_residential=True, asn_age_days=3650)
        young = _score_ip_reputation(is_residential=True, asn_age_days=30)
        assert young < old

    def test_mobile_scores_higher(self) -> None:
        mobile = _score_ip_reputation(is_mobile=True, is_residential=False)
        desktop = _score_ip_reputation(is_residential=False)
        assert mobile > desktop

    def test_classify_good(self) -> None:
        assert _classify_ip_quality(0.85) == "good"

    def test_classify_fair(self) -> None:
        assert _classify_ip_quality(0.55) == "fair"

    def test_classify_poor(self) -> None:
        assert _classify_ip_quality(0.2) == "poor"

    def test_score_bounds_are_clamped(self) -> None:
        for _ in range(100):
            score = _score_ip_reputation(
                is_tor=bool(_ % 2),
                is_proxy=True,
                previous_blocks=20,
                abuse_reports=30,
            )
            assert 0.0 <= score <= 1.0

    def test_multiple_negative_factors_stack(self) -> None:
        stacked = _score_ip_reputation(
            is_datacenter=True,
            is_vpn=True,
            is_proxy=True,
            is_residential=False,
            previous_blocks=5,
        )
        clean = _score_ip_reputation(is_residential=True)
        assert stacked < clean * 0.5

    def test_empty_reputation_is_good(self) -> None:
        score = _score_ip_reputation()
        assert score > 0.8

    def test_worst_case_score(self) -> None:
        score = _score_ip_reputation(
            is_datacenter=True,
            is_vpn=True,
            is_proxy=True,
            is_tor=True,
            is_residential=False,
            is_mobile=False,
            asn_age_days=1,
            previous_blocks=10,
            abuse_reports=20,
        )
        assert score <= 0.05, f"Worst-case score should be near 0, got {score}"
