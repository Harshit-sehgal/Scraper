"""Obs 4: Extraction cascade telemetry — test cascade layer logging per extraction."""

from __future__ import annotations

from typing import Any


def _build_cascade_entry(
    url: str,
    layers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a cascade telemetry entry for a URL.

    Each layer has: name, attempted, succeeded, quality_score, duration_ms.
    """
    return {
        "url": url,
        "total_layers": len(layers),
        "layers": layers,
        "winning_layer": next((layer["name"] for layer in reversed(layers) if layer["succeeded"]), None),
        "best_quality": max((layer["quality_score"] for layer in layers if layer["succeeded"]), default=0.0),
        "cascade_stopped_reason": _determine_stop_reason(layers),
    }


def _determine_stop_reason(layers: list[dict[str, Any]]) -> str:
    """Determine why the cascade stopped."""
    if not layers:
        return "no_layers"
    if any(layer["succeeded"] for layer in layers):
        return "layer_succeeded"
    if any(layer.get("error") for layer in layers):
        return "all_layers_failed"
    return "no_layers_attempted"


class TestCascadeTelemetryStructure:
    def test_single_layer_structure(self) -> None:
        entry = _build_cascade_entry(
            "https://example.com",
            [
                {"name": "regex", "attempted": True, "succeeded": True, "quality_score": 0.8, "duration_ms": 100},
            ],
        )
        assert entry["total_layers"] == 1
        assert entry["winning_layer"] == "regex"
        assert entry["best_quality"] == 0.8
        assert entry["cascade_stopped_reason"] == "layer_succeeded"


class TestCascadeMultiLayer:
    def test_multiple_layers_tracked(self) -> None:
        entry = _build_cascade_entry(
            "https://example.com",
            [
                {"name": "regex", "attempted": True, "succeeded": False, "quality_score": 0.2, "duration_ms": 50},
                {"name": "llm", "attempted": True, "succeeded": True, "quality_score": 0.9, "duration_ms": 500},
            ],
        )
        assert entry["total_layers"] == 2
        assert entry["winning_layer"] == "llm"

    def test_all_layers_fail(self) -> None:
        entry = _build_cascade_entry(
            "https://example.com",
            [
                {
                    "name": "regex",
                    "attempted": True,
                    "succeeded": False,
                    "quality_score": 0.0,
                    "duration_ms": 10,
                    "error": "no_match",
                },
                {
                    "name": "llm",
                    "attempted": True,
                    "succeeded": False,
                    "quality_score": 0.0,
                    "duration_ms": 100,
                    "error": "timeout",
                },
            ],
        )
        assert entry["winning_layer"] is None
        assert entry["best_quality"] == 0.0

    def test_best_quality_selected(self) -> None:
        entry = _build_cascade_entry(
            "https://example.com",
            [
                {"name": "regex", "attempted": True, "succeeded": True, "quality_score": 0.5, "duration_ms": 50},
                {"name": "llm", "attempted": True, "succeeded": True, "quality_score": 0.95, "duration_ms": 200},
            ],
        )
        assert entry["best_quality"] == 0.95

    def test_no_succeeding_layers_best_quality_zero(self) -> None:
        entry = _build_cascade_entry(
            "https://example.com",
            [
                {"name": "regex", "attempted": True, "succeeded": False, "quality_score": 0.0, "duration_ms": 10},
            ],
        )
        assert entry["best_quality"] == 0.0


class TestCascadeStopReason:
    def test_reason_layer_succeeded(self) -> None:
        entry = _build_cascade_entry(
            "https://example.com",
            [
                {"name": "regex", "attempted": True, "succeeded": True, "quality_score": 0.7, "duration_ms": 50},
            ],
        )
        assert entry["cascade_stopped_reason"] == "layer_succeeded"

    def test_reason_all_failed(self) -> None:
        entry = _build_cascade_entry(
            "https://example.com",
            [
                {"name": "regex", "attempted": True, "succeeded": False, "quality_score": 0.0, "duration_ms": 10, "error": "err"},
            ],
        )
        assert entry["cascade_stopped_reason"] == "all_layers_failed"

    def test_empty_layers(self) -> None:
        entry = _build_cascade_entry("https://example.com", [])
        assert entry["cascade_stopped_reason"] == "no_layers"


class TestCascadeTelemetryManyUrls:
    def test_multiple_urls_telemetry(self) -> None:
        urls = [
            _build_cascade_entry(
                "https://a.com/1",
                [{"name": "regex", "attempted": True, "succeeded": True, "quality_score": 0.9, "duration_ms": 30}],
            ),
            _build_cascade_entry(
                "https://b.com/1",
                [{"name": "llm", "attempted": True, "succeeded": True, "quality_score": 0.85, "duration_ms": 200}],
            ),
        ]
        assert len(urls) == 2
        assert urls[0]["url"] == "https://a.com/1"
        assert urls[1]["winning_layer"] == "llm"
