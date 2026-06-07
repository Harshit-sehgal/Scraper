"""Tests for the Grafana dashboard JSON — structural and schema validation.

Enforces invariants on ``grafana/dashboards/dataforge_overview.json`` so
that manual edits to the dashboard (adding panels, adjusting grid
positions, changing metric expressions) cannot silently corrupt the
dashboard definition. Covers:

- Valid JSON and presence of all required top-level metadata fields
- Unique panel IDs (no duplicates)
- Grid position integrity: panels must fit within the 24-column
  Grafana grid and must not overlap
- Required per-panel fields (title, type, gridPos, at least one target)
- All Prometheus metric names referenced in ``targets[*].expr`` match
  the expected ``dataforge_`` prefix pattern
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DASHBOARD_PATH = Path(__file__).parents[2] / "grafana" / "dashboards" / "dataforge_overview.json"
GRID_COLUMNS = 24  # Grafana uses a 24-column grid


# ── Helpers ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def dashboard() -> dict:
    """Load and parse the Grafana dashboard JSON once per module."""
    with open(DASHBOARD_PATH, encoding="utf-8") as f:
        return json.load(f)


_PROMETHEUS_METRIC_RE = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")


def _extract_metric_names(expr: str) -> list[str]:
    """Extract Prometheus metric names from a PromQL expression.

    Prometheus metric names match ``[a-zA-Z_:][a-zA-Z0-9_:]*`` and
    appear before ``{``, ``[``, or operators. We split on whitespace
    and operators, then filter for likely metric names.
    """
    # Remove string literals (single-quoted) to avoid false matches
    cleaned = re.sub(r"'[^']*'", "", expr)
    candidates = _PROMETHEUS_METRIC_RE.findall(cleaned)
    # Filter to names that look like metrics (contain at least one letter
    # and aren't PromQL keywords / scalar operators)
    keywords = {
        "or",
        "and",
        "unless",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "offset",
        "bool",
        "by",
        "without",
        "le",  # Reserved histogram bucket label
    }
    return [
        m
        for m in candidates
        if any(c.isalpha() for c in m)
        and m not in keywords
        and not m.startswith("$")
        # Exclude single-letter tokens (these are PromQL duration units
        # like ``m``, ``h``, ``s``, ``d`` appearing in range selectors
        # such as ``[5m]`` or ``[1h]``).
        and len(m) > 1
        # Exclude PromQL functions: a function is always ``name(``,
        # while a metric is ``name{`` or ``name[`` or at expression end.
        and not re.search(re.escape(m) + r"\s*\(", expr)
        # Exclude PromQL label keys: a label key inside a ``{...}``
        # selector is always preceded by ``{`` or ``,`` and followed
        # by one of ``=``, ``!=``, ``=~``, ``!~`` (e.g.
        # ``{status='failed'}`` or ``{type!='database'}``). This does
        # NOT match metric names used with comparison operators like
        # ``metric == 1`` because the ``=`` in ``==`` is not preceded
        # by ``{`` or ``,``.
        and not re.search(r"(?:[,{])\s*" + re.escape(m) + r"\s*[!=~]", expr)
    ]


# ── Top-level Structure ─────────────────────────────────────────────────


class TestDashboardMetadata:
    """Verify the dashboard JSON has the expected top-level keys and values."""

    REQUIRED_KEYS = {"title", "uid", "version", "schemaVersion", "tags", "timezone", "editable", "refresh", "panels"}

    def test_required_keys_present(self, dashboard: dict) -> None:
        missing = self.REQUIRED_KEYS - dashboard.keys()
        assert not missing, f"Dashboard is missing required keys: {missing}"

    def test_uid_is_stable(self, dashboard: dict) -> None:
        assert dashboard.get("uid") == "dataforge-overview", "Dashboard UID must remain 'dataforge-overview'"

    def test_title_is_set(self, dashboard: dict) -> None:
        assert isinstance(dashboard.get("title"), str) and dashboard["title"].strip(), "Title must be non-empty"

    def test_refresh_is_reasonable(self, dashboard: dict) -> None:
        refresh = dashboard.get("refresh", "")
        assert isinstance(refresh, str) and refresh, "refresh must be a non-empty string"
        # Parse: "30s", "1m", "5m" etc.
        unit = refresh[-1]
        assert unit in ("s", "m", "h"), f"Unrecognized refresh unit: {unit}"
        value = int(refresh[:-1])
        assert 5 <= value <= 300, f"Refresh interval {refresh} seems unreasonable"

    def test_panels_is_list(self, dashboard: dict) -> None:
        panels = dashboard.get("panels", [])
        assert isinstance(panels, list), "panels must be a list"
        assert len(panels) > 0, "panels list must not be empty"


# ── Panel IDs ───────────────────────────────────────────────────────────


class TestPanelIds:
    """Validate panel IDs are unique and sequential (within reason)."""

    def test_all_ids_unique(self, dashboard: dict) -> None:
        ids = [p["id"] for p in dashboard["panels"] if "id" in p]
        duplicates = {i for i in ids if ids.count(i) > 1}
        assert not duplicates, f"Duplicate panel IDs found: {duplicates}"

    def test_ids_are_positive_integers(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            pid = panel.get("id")
            assert isinstance(pid, int) and pid > 0, f"Panel '{panel.get('title', '?')}' has invalid id: {pid}"


# ── Grid Positions ──────────────────────────────────────────────────────


class TestGridPositions:
    """Verify that panels do not overlap within the 24-column Grafana grid.

    Each panel occupies a rectangle from (x, y) to (x + w, y + h).
    We collect all occupied rectangles and check for overlap.
    """

    def _panel_rect(self, panel: dict) -> tuple[int, int, int, int]:
        gp = panel.get("gridPos", {})
        return (gp["x"], gp["y"], gp["x"] + gp["w"], gp["y"] + gp["h"])

    def _rects_overlap(self, a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
        """Two rectangles (x1,y1,x2,y2) overlap if neither is fully to the
        left, right, above, or below the other."""
        return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]

    def test_all_panels_have_gridpos(self, dashboard: dict) -> None:
        missing = [p.get("title", f"id={p.get('id', '?')}") for p in dashboard["panels"] if "gridPos" not in p]
        assert not missing, f"Panels missing gridPos: {missing}"

    def test_width_fits_grid(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            gp = panel.get("gridPos", {})
            w = gp.get("w", 0)
            x = gp.get("x", 0)
            assert x + w <= GRID_COLUMNS, (
                f"Panel '{panel.get('title', '?')}' (id={panel.get('id')}) overflows grid: x={x} + w={w} > {GRID_COLUMNS}"
            )

    def test_no_panels_overlap(self, dashboard: dict) -> None:
        rects = [(p.get("id", 0), self._panel_rect(p)) for p in dashboard["panels"]]
        for i, (id_a, rect_a) in enumerate(rects):
            for j, (id_b, rect_b) in enumerate(rects):
                if i >= j:
                    continue
                if self._rects_overlap(rect_a, rect_b):
                    title_a = dashboard["panels"][i].get("title", "?")
                    title_b = dashboard["panels"][j].get("title", "?")
                    pytest.fail(
                        f"Panel overlap: '{title_a}' (id={id_a}, rect={rect_a}) and '{title_b}' (id={id_b}, rect={rect_b})"
                    )

    def test_dimensions_are_positive(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            gp = panel.get("gridPos", {})
            assert gp.get("w", 0) > 0, f"Panel '{panel.get('title', '?')}' has zero width"
            assert gp.get("h", 0) > 0, f"Panel '{panel.get('title', '?')}' has zero height"


# ── Per-panel Required Fields ──────────────────────────────────────────


class TestPanelFields:
    """Each panel must have at least title, type, and one target."""

    def test_every_panel_has_title(self, dashboard: dict) -> None:
        untitled = [p for p in dashboard["panels"] if not isinstance(p.get("title"), str) or not p["title"].strip()]
        assert not untitled, f"Panel(s) missing title: {[p.get('id') for p in untitled]}"

    def test_every_panel_has_type(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            assert isinstance(panel.get("type"), str) and panel["type"].strip(), (
                f"Panel '{panel.get('title', '?')}' (id={panel.get('id')}) is missing 'type'"
            )

    def test_every_panel_has_at_least_one_target(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            targets = panel.get("targets", [])
            assert len(targets) >= 1, f"Panel '{panel.get('title', '?')}' (id={panel.get('id')}) has no targets"

    def test_every_target_has_expr(self, dashboard: dict) -> None:
        for panel in dashboard["panels"]:
            for t in panel.get("targets", []):
                assert isinstance(t.get("expr"), str) and t["expr"].strip(), (
                    f"Panel '{panel.get('title', '?')}' (id={panel.get('id')}) has target without expr"
                )


# ── Prometheus Metric Names ─────────────────────────────────────────────


class TestMetricNames:
    """Validate that referenced Prometheus metrics use the ``dataforge_`` prefix.

    This prevents accidentally referencing external metrics (like
    Prometheus's built-in ``up``) without explicit documentation. Known
    external metrics (``up``, ``process_resident_memory_bytes``) are
    allowlisted.
    """

    ALLOWLISTED_EXTERNAL = {
        "up",  # Prometheus built-in service liveness
        "process_resident_memory_bytes",  # Standard process exporter metric
    }

    def test_all_metrics_have_allowed_prefix(self, dashboard: dict) -> None:
        bad = []
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                for metric in _extract_metric_names(expr):
                    if metric in self.ALLOWLISTED_EXTERNAL:
                        continue
                    if not metric.startswith("dataforge_"):
                        bad.append(f"  Panel '{panel.get('title', '?')}': references '{metric}' (should be dataforge_*)")
        assert not bad, "Non-dataforge metric references found:\n" + "\n".join(bad)


# ── Dashboard Links ────────────────────────────────────────────────────


class TestDashboardLinks:
    """Dashboard links should point to valid resources."""

    def test_links_have_title_and_url(self, dashboard: dict) -> None:
        for link in dashboard.get("links", []):
            assert isinstance(link.get("title"), str) and link["title"].strip(), f"Link missing title: {link}"
            assert isinstance(link.get("url"), str) and link["url"].strip(), f"Link '{link.get('title')}' missing url"

    def test_at_least_one_link(self, dashboard: dict) -> None:
        links = dashboard.get("links", [])
        assert len(links) >= 1, "Dashboard should have at least one link"
