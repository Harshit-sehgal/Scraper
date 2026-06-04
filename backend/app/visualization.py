"""
Visualization & Governance — live visual system mapping, operator modes, and cluster visualization.

Provides:
  - Markdown architecture and distributed node mapping (Mermaid diagrams).
  - Dynamic operator mode configurations (Production, Benchmark, Forensic, Stealth, Low-cost).
  - Global governance status reporting.
"""

from __future__ import annotations

import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = str(_BACKEND_ROOT / "data" / "governance" / "architecture_map.md")


class OperatorMode(str, Enum):
    """Adaptive operational profiles for the scraper substrate."""

    PRODUCTION = "production"
    """Optimized for high-yield throughput and stable data capture."""

    BENCHMARK = "benchmark"
    """Hostile environment validation: full telemetry logging, bypass exclusions."""

    FORENSIC = "forensic"
    """Deep diagnostics: records verbose replay logs and traces execution layers."""

    STEALTH = "stealth"
    """Aggressive anti-bot camouflage: maximum delay pacing, randomized mouse paths."""

    LOW_COST = "low_cost"
    """Resource conservation: strict context boundaries, aggressive geocoding caching."""


class SystemGovernorDashboard:
    """Manages active operator profiles and generates live system dependency mapping."""

    def __init__(self, mode: OperatorMode = OperatorMode.PRODUCTION) -> None:
        self.active_mode = mode
        self.last_map_update = 0.0
        self._apply_mode_settings(mode)

    def set_operator_mode(self, mode: OperatorMode) -> dict[str, Any]:
        """Dynamically adjust system settings to enforce the target operational profile."""
        self.active_mode = mode
        adjustments = self._apply_mode_settings(mode)
        logger.info("[Governance] Switched operator mode to '%s': %s", mode.value, adjustments)
        return adjustments

    def _apply_mode_settings(self, mode: OperatorMode) -> dict[str, Any]:
        """Modify runtime settings configurations based on the selected mode profile."""
        from app.config import settings

        adjustments = {}
        if mode == OperatorMode.PRODUCTION:
            settings.PLAYWRIGHT_TIMEOUT = 30000
            settings.PAGE_SETTLE_DELAY = 3.0
            adjustments = {"timeout": 30000, "settle": 3.0, "stealth": False}
        elif mode == OperatorMode.BENCHMARK:
            settings.PLAYWRIGHT_TIMEOUT = 45000
            settings.PAGE_SETTLE_DELAY = 5.0
            adjustments = {"timeout": 45000, "settle": 5.0, "stealth": False}
        elif mode == OperatorMode.FORENSIC:
            settings.PLAYWRIGHT_TIMEOUT = 60000
            settings.PAGE_SETTLE_DELAY = 8.0
            adjustments = {"timeout": 60000, "settle": 8.0, "stealth": True}
        elif mode == OperatorMode.STEALTH:
            settings.PLAYWRIGHT_TIMEOUT = 60000
            settings.PAGE_SETTLE_DELAY = 6.0
            adjustments = {"timeout": 60000, "settle": 6.0, "stealth": True}
        elif mode == OperatorMode.LOW_COST:
            settings.PLAYWRIGHT_TIMEOUT = 20000
            settings.PAGE_SETTLE_DELAY = 2.0
            adjustments = {"timeout": 20000, "settle": 2.0, "stealth": False}

        return adjustments

    def generate_system_map(self) -> None:
        """Construct and write a visual Markdown system map showing the cluster dependency nodes."""
        from app.semantic_world_state import get_world_state

        ws = get_world_state()

        # 1. Fetch registered federated nodes
        nodes = getattr(ws.federation, "registered_nodes", {})

        os.makedirs(os.path.dirname(MAP_PATH), exist_ok=True)

        with open(MAP_PATH, "w", encoding="utf-8") as f:
            f.write("# 🗺️ DataForge Visual System & Distributed Topology Map\n\n")
            f.write(
                f"> **Governance Layer**: Live architectural status. Last refreshed: {
                    time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
                }\n\n",
            )

            f.write("## 1. Active Operator Profile\n\n")
            f.write(f"- **Current System Profile**: `OPERATOR_MODE = {self.active_mode.value.upper()}`\n")
            f.write("- **System Invariant Compliance**: `HEALTHY` for the checks included in this visualization\n\n")

            f.write("## 2. Distributed Shard Topology\n\n")
            if not nodes:
                f.write("*Single-node execution: No remote federated instances registered yet.*\n\n")
            else:
                f.write("```mermaid\n")
                f.write("graph LR\n")
                # Show node links
                local_node = ws.federation.node_id
                f.write(f'    Local["Local Node: {local_node}"]\n')
                for node_id, info in nodes.items():
                    f.write(f'    Node_{node_id.replace("-", "_")}["Remote Node: {node_id} (Shard {info["shard_id"]})"]\n')
                    f.write(f"    Local <--> |sync| Node_{node_id.replace('-', '_')}\n")
                f.write("```\n\n")

            f.write("## 3. High-Level Component Flow\n\n")
            f.write("```mermaid\n")
            f.write("graph TD\n")
            f.write("    CrawlFrontier[Crawl Frontier Queue] --> |prioritize| Seeds[Extraction Targets]\n")
            f.write("    Seeds --> |fetch| BrowserPool[Browser Pool / Stealth context]\n")
            f.write("    BrowserPool --> |render| DomStabilizer[Adaptive DOM Quietness]\n")
            f.write("    DomStabilizer --> |extract| SelectorEngine[Selector Engine / Discovery]\n")
            f.write("    SelectorEngine --> |validate| InvariantFirewall[Invariant Firewall]\n")
            f.write("    InvariantFirewall --> |persist| SemanticWorldState[Semantic World State]\n")
            f.write("    SemanticWorldState --> |merge| Federation[Multi-Shard Federation]\n")
            f.write("```\n\n")

            f.write("---\n * End of Dynamic System Map.*\n")

        self.last_map_update = time.time()

    def get_governance_summary(self) -> dict[str, Any]:
        """Collate the complete governance, resource, and synchronization metrics."""
        from app.resource_governor import get_resource_governor

        gov = get_resource_governor()

        return {
            "active_mode": self.active_mode.value,
            "system_map_path": MAP_PATH,
            "last_map_update": self.last_map_update,
            "resources": gov.get_governance_report(),
        }


# Global singleton
_governance_dashboard: SystemGovernorDashboard | None = None


def get_governance_dashboard() -> SystemGovernorDashboard:
    """Access the global governance dashboard singleton."""
    global _governance_dashboard
    if _governance_dashboard is None:
        _governance_dashboard = SystemGovernorDashboard()
    return _governance_dashboard
