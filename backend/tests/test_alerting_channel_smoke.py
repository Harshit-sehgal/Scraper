"""Guard tests for the F-MON-001 alerting channel wiring.

The pre-fix ``scripts/smoke_prod_stack.sh`` only checked Alertmanager
readiness (``/-/ready``) — which serves HTTP 200 even when the
``smtp_smarthost`` AND ``slack_api_url`` are both empty strings.
Alertmanager v0.27+ silently drops alerts in that state, so the
production smoke claimed "Alertmanager OK" while the alerting
pipeline swallowed every page.

The fix:

- A new pre-drill check reads ``.env.production`` (falling back to
  ``.env``) and asserts that at least one of
  ``ALERTMANAGER_SMTP_HOST`` or ``ALERTMANAGER_SLACK_WEBHOOK_URL``
  is configured. With both empty the smoke fails closed.
- A follow-up drill runs ``scripts/run_alert_delivery_drill.py``
  inside the dataforge container and asserts that Alertmanager's
  ``/api/v2/alerts`` accepts the synthetic alert (a regression
  sentinel for broken ``web.external-url`` or routing).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "smoke_prod_stack.sh"
DRILL_SCRIPT = REPO_ROOT / "scripts" / "run_alert_delivery_drill.py"


def _smoke_text() -> str:
    assert SMOKE_SCRIPT.is_file(), f"missing {SMOKE_SCRIPT}"
    return SMOKE_SCRIPT.read_text(encoding="utf-8")


class TestAlertingChannelWiring:
    """The smoke script asserts at least one notification channel."""

    def test_smoke_references_required_channel_env_vars(self) -> None:
        text = _smoke_text()
        # The smoke must check both expected channel env vars.
        assert "ALERTMANAGER_SMTP_HOST" in text, (
            "smoke_prod_stack.sh no longer references ALERTMANAGER_SMTP_HOST"
        )
        assert "ALERTMANAGER_SLACK_WEBHOOK_URL" in text, (
            "smoke_prod_stack.sh no longer references ALERTMANAGER_SLACK_WEBHOOK_URL"
        )

    def test_smoke_fails_closed_when_both_channels_missing(self) -> None:
        text = _smoke_text()
        # The proof of fail-closed is the empty-both branch. Look for
        # the diagnostic phrase that operators see on a refused deploy.
        # The phrase uses ``FAIL`` token plus the deterministic "No
        # alerting channel configured" message.
        assert "No alerting channel configured" in text, (
            "smoke_prod_stack.sh: missing the fail-closed message that surfaces "
            "when neither channel is set"
        )
        # And it must read ``.env.production`` (or fall back to ``.env``)
        # so the assertion runs against the deploy's actual config.
        assert ".env.production" in text or ".env" in text, (
            "smoke_prod_stack.sh does not read .env.production / .env"
        )

    def test_smoke_runs_synthetic_alert_drill(self) -> None:
        text = _smoke_text()
        assert "run_alert_delivery_drill.py" in text, (
            "smoke_prod_stack.sh no longer wires run_alert_delivery_drill.py"
        )
        # Drill is invoked against the in-network Alertmanager endpoint.
        assert "http://alertmanager:9093" in text, (
            "smoke_prod_stack.sh: drill must target the in-network Alertmanager URL"
        )


class TestSmokeSyntaxAndPeripherals:
    """The smoke script still parses and references the drill file."""

    def test_bash_syntax_parses(self) -> None:
        import subprocess

        result = subprocess.run(
            ["bash", "-n", str(SMOKE_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"smoke_prod_stack.sh has bash syntax errors: {result.stderr}"
        )

    def test_drill_script_exists(self) -> None:
        assert DRILL_SCRIPT.is_file(), (
            f"missing {DRILL_SCRIPT} (referenced from smoke_prod_stack.sh)"
        )
