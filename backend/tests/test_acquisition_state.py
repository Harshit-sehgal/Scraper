"""Tests for AcquisitionState and AcquisitionLineage."""

from app.acquisition_state import AcquisitionLineage, AcquisitionState
from app.selector_discovery import build_redirect_info


class TestAcquisitionState:
    """Tests for the AcquisitionState enum."""

    def test_all_states_have_string_values(self) -> None:
        for state in AcquisitionState:
            assert isinstance(state.value, str)
            assert state.value  # non-empty

    def test_direct_state(self) -> None:
        assert AcquisitionState.DIRECT.value == "direct"

    def test_session_expired_state(self) -> None:
        assert AcquisitionState.SESSION_EXPIRED.value == "session_expired"

    def test_recovered_state(self) -> None:
        assert AcquisitionState.RECOVERED.value == "recovered"


class TestAcquisitionLineage:
    """Tests for the AcquisitionLineage model."""

    def test_direct_lineage_to_dict(self) -> None:
        lineage = AcquisitionLineage(
            original_url="https://example.com/data",
            final_url="https://example.com/data",
            state=AcquisitionState.DIRECT,
            message="No redirect detected",
            fetch_method="playwright_full",
        )
        d = lineage.to_dict()
        assert d["redirected"] is False
        assert d["redirect_type"] == "none"
        assert d["original_url"] == "https://example.com/data"
        assert d["final_url"] == "https://example.com/data"

    def test_session_expired_lineage_to_dict(self) -> None:
        lineage = AcquisitionLineage(
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/",
            state=AcquisitionState.SESSION_EXPIRED,
            message="URL redirected to homepage — session expired",
            fetch_method="playwright_full",
        )
        d = lineage.to_dict()
        assert d["redirected"] is True
        assert d["redirect_type"] == "session_expired"

    def test_recovered_lineage_to_dict(self) -> None:
        lineage = AcquisitionLineage(
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/search?from=NYC&to=LHR",
            state=AcquisitionState.RECOVERED,
            message="Search session was recovered via form submission",
            fetch_method="search_form_post",
            recovery_method="search_form_post",
            recovered_url="https://example.com/search?from=NYC&to=LHR",
        )
        d = lineage.to_dict()
        assert d["redirected"] is False
        assert d["redirect_type"] == "none"
        assert "recovered" in d["message"].lower()

    def test_recovery_failed_lineage_to_dict(self) -> None:
        lineage = AcquisitionLineage(
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/",
            state=AcquisitionState.RECOVERY_FAILED,
            message="Session expired and recovery failed",
            fetch_method="playwright_full",
        )
        d = lineage.to_dict()
        assert d["redirected"] is True
        assert d["redirect_type"] == "session_expired"

    def test_from_redirect_info_no_redirect(self) -> None:
        redirect_info = {
            "redirected": False,
            "redirect_type": "none",
            "message": "No redirect detected",
            "original_url": "https://example.com/data",
            "final_url": "https://example.com/data",
        }
        lineage = AcquisitionLineage.from_redirect_info(
            redirect_info,
            original_url="https://example.com/data",
            final_url="https://example.com/data",
            fetch_method="playwright_full",
        )
        assert lineage.state == AcquisitionState.DIRECT
        assert lineage.final_url == "https://example.com/data"

    def test_from_redirect_info_session_expired_no_recovery(self) -> None:
        redirect_info = {
            "redirected": True,
            "redirect_type": "session_expired",
            "message": "URL redirected to homepage — session expired",
            "original_url": "https://example.com/search/abc123",
            "final_url": "https://example.com/",
        }
        lineage = AcquisitionLineage.from_redirect_info(
            redirect_info,
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/",
            fetch_method="playwright_full",
        )
        assert lineage.state == AcquisitionState.SESSION_EXPIRED

    def test_from_redirect_info_session_expired_with_successful_recovery(self) -> None:
        redirect_info = {
            "redirected": True,
            "redirect_type": "session_expired",
            "message": "URL redirected to homepage — session expired",
            "original_url": "https://example.com/search/abc123",
            "final_url": "https://example.com/",
        }
        search_recovery = {
            "success": True,
            "fresh_url": "https://example.com/search?from=NYC&to=LHR",
            "fresh_html": "<html>results</html>",
            "form_detected": True,
            "error": None,
        }
        lineage = AcquisitionLineage.from_redirect_info(
            redirect_info,
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/search?from=NYC&to=LHR",
            fetch_method="search_form_post",
            search_recovery=search_recovery,
        )
        assert lineage.state == AcquisitionState.RECOVERED
        assert lineage.recovery_method == "search_form_post"
        assert lineage.recovered_url == "https://example.com/search?from=NYC&to=LHR"

    def test_from_redirect_info_session_expired_awaiting_params(self) -> None:
        redirect_info = {
            "redirected": True,
            "redirect_type": "session_expired",
            "message": "URL redirected to homepage — session expired",
            "original_url": "https://example.com/search/abc123",
            "final_url": "https://example.com/",
        }
        search_form = {
            "detected": True,
            "action": "/search",
            "method": "POST",
            "fields": [{"name": "from"}, {"name": "to"}],
            "search_fields": [{"name": "from"}, {"name": "to"}],
        }
        lineage = AcquisitionLineage.from_redirect_info(
            redirect_info,
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/",
            fetch_method="playwright_full",
            search_form=search_form,
            search_params=None,
        )
        assert lineage.state == AcquisitionState.AWAITING_SEARCH_PARAMS

    def test_from_redirect_info_session_expired_no_search_form(self) -> None:
        redirect_info = {
            "redirected": True,
            "redirect_type": "session_expired",
            "message": "URL redirected to homepage — session expired",
            "original_url": "https://example.com/search/abc123",
            "final_url": "https://example.com/",
        }
        lineage = AcquisitionLineage.from_redirect_info(
            redirect_info,
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/",
            fetch_method="playwright_full",
            search_form={"detected": False},
        )
        assert lineage.state == AcquisitionState.NO_SEARCH_FORM

    def test_from_redirect_info_recovery_message_in_non_redirected(self) -> None:
        """When redirect_info says not redirected but message mentions recovery,
        infer RECOVERED state.
        """
        redirect_info = {
            "redirected": False,
            "redirect_type": "none",
            "message": "Search session was recovered via form submission → fresh results page",
            "original_url": "https://example.com/search/abc123",
            "final_url": "https://example.com/search?from=NYC&to=LHR",
        }
        lineage = AcquisitionLineage.from_redirect_info(
            redirect_info,
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/search?from=NYC&to=LHR",
            fetch_method="search_form_post",
        )
        assert lineage.state == AcquisitionState.RECOVERED
        assert lineage.recovery_method == "search_form_post"

    def test_from_redirect_info_path_changed(self) -> None:
        redirect_info = {
            "redirected": True,
            "redirect_type": "path_changed",
            "message": "URL path changed",
            "original_url": "https://example.com/old-path",
            "final_url": "https://example.com/new-path",
        }
        lineage = AcquisitionLineage.from_redirect_info(
            redirect_info,
            original_url="https://example.com/old-path",
            final_url="https://example.com/new-path",
        )
        assert lineage.state == AcquisitionState.PATH_CHANGED

    def test_from_redirect_info_homepage_redirect(self) -> None:
        redirect_info = {
            "redirected": True,
            "redirect_type": "homepage_redirect",
            "message": "URL redirected to the site homepage",
            "original_url": "https://example.com/old",
            "final_url": "https://example.com/",
        }
        lineage = AcquisitionLineage.from_redirect_info(
            redirect_info,
            original_url="https://example.com/old",
            final_url="https://example.com/",
        )
        assert lineage.state == AcquisitionState.HOMEPAGE_REDIRECT


class TestBuildRedirectInfo:
    """Tests for the build_redirect_info helper function."""

    def test_direct_url(self) -> None:
        result = build_redirect_info(
            original_url="https://example.com/data",
            final_url="https://example.com/data",
        )
        assert result["redirected"] is False
        assert result["redirect_type"] == "none"

    def test_session_expired_with_recovery(self) -> None:
        initial_redirect = {
            "redirected": True,
            "redirect_type": "session_expired",
            "message": "URL redirected to homepage — session expired",
            "original_url": "https://example.com/search/abc123",
            "final_url": "https://example.com/",
        }
        search_recovery = {
            "success": True,
            "fresh_url": "https://example.com/search?from=NYC&to=LHR",
            "fresh_html": "<html>results</html>",
            "form_detected": True,
            "error": None,
        }
        result = build_redirect_info(
            original_url="https://example.com/search/abc123",
            final_url="https://example.com/search?from=NYC&to=LHR",
            search_recovery=search_recovery,
            fetch_method="search_form_post",
            existing_redirect_info=initial_redirect,
        )
        assert result["redirected"] is False
        assert result["redirect_type"] == "none"
        assert "recovered" in result["message"].lower()

    def test_session_expired_no_recovery(self) -> None:
        result = build_redirect_info(
            original_url="https://example.com/search/results/abc123",
            final_url="https://example.com/",
        )
        assert result["redirected"] is True
        assert result["redirect_type"] == "session_expired"
