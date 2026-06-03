# mypy: ignore-errors
# type: ignore
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventMixin:
    def _on_field_wave(self, event: Any) -> None:
        """Handle a field wave by processing it within a transaction."""
        if self._replaying:
            return

        source_id = event.payload.get("source_id")
        intensity = event.payload.get("intensity", 0.0)

        if source_id and intensity > 0:
            # We use a separate transaction for the wave processing
            # to ensure causality is tracked correctly.
            with self.transaction(label=f"wave_processing:{source_id}"):
                self._topology.process_field_wave(source_id, intensity)
