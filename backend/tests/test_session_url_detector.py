"""Tests for session URL detection and ephemeral parameter stripping."""

from app.session_url_detector import detect_session_params, strip_session_params


class TestDetectSessionParams:
    """Tests for detect_session_params()."""

    def test_clean_url_no_session_params(self):
        result = detect_session_params("https://example.com/flights?origin=NYC&destination=LHR")
        assert result["is_session_bound"] is False
        assert result["ephemeral_params"] == []
        assert result["canonical_url"] == "https://example.com/flights?origin=NYC&destination=LHR"

    def test_url_with_session_id(self):
        result = detect_session_params(
            "https://example.com/search?sessionid=abc123&origin=NYC"
        )
        assert result["is_session_bound"] is True
        assert "sessionid" in result["ephemeral_params"]
        assert "origin=NYC" in result["canonical_url"]
        assert "sessionid" not in result["canonical_url"]

    def test_url_with_utm_params(self):
        result = detect_session_params(
            "https://example.com/data?utm_source=google&utm_medium=cpc&category=flights"
        )
        assert result["is_session_bound"] is True
        assert "utm_source" in result["ephemeral_params"]
        assert "utm_medium" in result["ephemeral_params"]
        assert "category" not in result["ephemeral_params"]
        assert "category=flights" in result["canonical_url"]

    def test_url_with_uuid_value(self):
        result = detect_session_params(
            "https://example.com/search?id=550e8400-e29b-41d4-a716-446655440000"
        )
        assert result["is_session_bound"] is True
        assert "id" in result["ephemeral_params"]

    def test_url_with_long_hex_value(self):
        result = detect_session_params(
            "https://example.com/results?token=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        )
        assert result["is_session_bound"] is True
        assert "token" in result["ephemeral_params"]

    def test_url_with_fbclid(self):
        result = detect_session_params(
            "https://example.com/page?fbclid=IwAR123abc&category=shoes"
        )
        assert result["is_session_bound"] is True
        assert "fbclid" in result["ephemeral_params"]
        assert "category" not in result["ephemeral_params"]

    def test_url_with_csrf_token(self):
        result = detect_session_params(
            "https://example.com/form?csrf_token=xyz789&field=value"
        )
        assert result["is_session_bound"] is True
        assert "csrf_token" in result["ephemeral_params"]

    def test_url_with_path_hash_segment(self):
        result = detect_session_params(
            "https://example.com/search/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        )
        assert result["is_session_bound"] is True
        assert result["confidence"] >= 0.6
        assert len(result["ephemeral_params"]) >= 1
        assert any("path:/" in p for p in result["ephemeral_params"])

    def test_url_without_query_params(self):
        result = detect_session_params("https://example.com/flights/LAX-LHR")
        assert result["is_session_bound"] is False
        assert result["ephemeral_params"] == []
        assert result["canonical_url"] == "https://example.com/flights/LAX-LHR"

    def test_confidence_high_for_session_id(self):
        result = detect_session_params(
            "https://example.com/page?sessionid=abc123"
        )
        assert result["confidence"] >= 0.8

    def test_confidence_low_for_regular_params(self):
        result = detect_session_params(
            "https://example.com/page?category=flights&sort=price"
        )
        assert result["confidence"] < 0.5

    def test_multiple_session_params(self):
        result = detect_session_params(
            "https://example.com/search?sessionid=abc&utm_source=google&origin=NYC&token=xyz"
        )
        assert result["is_session_bound"] is True
        assert len(result["ephemeral_params"]) == 3
        assert "origin" not in result["ephemeral_params"]

    def test_details_explain_why(self):
        result = detect_session_params(
            "https://example.com/page?sessionid=abc"
        )
        assert len(result["details"]) >= 1
        param_name, reason = result["details"][0]
        assert param_name == "sessionid"
        assert "pattern" in reason.lower() or "matches" in reason.lower()


class TestStripSessionParams:
    """Tests for strip_session_params()."""

    def test_strips_session_id(self):
        canonical = strip_session_params(
            "https://example.com/search?sessionid=abc123&origin=NYC"
        )
        assert "sessionid" not in canonical
        assert "origin=NYC" in canonical

    def test_preserves_clean_url(self):
        canonical = strip_session_params(
            "https://example.com/flights?origin=NYC&destination=LHR"
        )
        assert canonical == "https://example.com/flights?origin=NYC&destination=LHR"

    def test_strips_all_tracking(self):
        canonical = strip_session_params(
            "https://example.com/data?utm_source=google&utm_medium=cpc&fbclid=abc&category=flights"
        )
        assert "utm_source" not in canonical
        assert "utm_medium" not in canonical
        assert "fbclid" not in canonical
        assert "category=flights" in canonical