#!/usr/bin/env python3
"""Synthetic Alertmanager drill for DataForge ops readiness.

This proves Alertmanager can accept and expose a synthetic alert. It
does not pretend to prove Slack/email delivery from API state alone:
use --notification-evidence after confirming the real on-call channel.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_ALERTMANAGER_URL = "http://localhost:9093"
DEFAULT_ALERTNAME = "DataForgeSyntheticAlertDrill"


@dataclass(frozen=True)
class AlertDrillConfig:
    alertmanager_url: str
    alertname: str
    severity: str
    drill_id: str
    timeout_seconds: float
    poll_interval_seconds: float
    alert_duration_seconds: int
    notification_evidence: str
    require_notification_evidence: bool
    channel_assert_reachable: bool
    slack_bot_token: str
    slack_channel_id: str
    extra_labels: dict[str, str]


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    body: str


@dataclass(frozen=True)
class SlackChannelCheckResult:
    reachable: bool
    reason: str


@dataclass(frozen=True)
class AlertDrillResult:
    generated_at: str
    alertmanager_url: str
    alertname: str
    severity: str
    drill_id: str
    ready_status_code: int
    post_status_code: int
    alert_visible: bool
    notification_delivery_confirmed: bool
    notification_evidence: str
    require_notification_evidence: bool
    slack_channel_check_required: bool
    slack_channel_reachable: bool
    slack_channel_check_reason: str
    passed: bool
    failure_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> datetime:
    return datetime.now(UTC)


def rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def normalize_base_url(raw: str) -> str:
    parsed = urllib.parse.urlparse(raw.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("Alertmanager URL must be an absolute http(s) URL")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def display_url(raw: str) -> str:
    parsed = urllib.parse.urlparse(raw)
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urllib.parse.urlunparse((parsed.scheme, netloc, parsed.path.rstrip("/"), "", "", ""))


def endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def parse_label(raw: str) -> tuple[str, str]:
    key, separator, value = raw.partition("=")
    key = key.strip()
    value = value.strip()
    if not separator or not key or not value:
        raise argparse.ArgumentTypeError(f"label must use key=value format: {raw!r}")
    return key, value


def build_alert_payload(config: AlertDrillConfig, *, starts_at: datetime | None = None) -> list[dict[str, Any]]:
    start = starts_at or utc_now()
    end = start + timedelta(seconds=config.alert_duration_seconds)
    labels = {
        "alertname": config.alertname,
        "severity": config.severity,
        "service": "dataforge",
        "source": "synthetic-alert-drill",
        "drill_id": config.drill_id,
        **config.extra_labels,
    }
    return [
        {
            "labels": labels,
            "annotations": {
                "summary": "DataForge synthetic alert drill",
                "description": (
                    "Synthetic alert posted by scripts/run_alert_delivery_drill.py. "
                    "Confirm Slack/email delivery separately before marking production alerting ready."
                ),
            },
            "startsAt": rfc3339(start),
            "endsAt": rfc3339(end),
            "generatorURL": "https://github.com/Harshit-sehgal/Scraper",
        }
    ]


def http_request(
    method: str,
    url: str,
    *,
    payload: Any | None = None,
    timeout_seconds: float = 10.0,
    headers: dict[str, str] | None = None,
) -> HttpResult:
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(1_000_000).decode("utf-8", errors="replace")
            return HttpResult(status_code=response.status, body=body)
    except urllib.error.HTTPError as exc:
        body = exc.read(1_000_000).decode("utf-8", errors="replace")
        return HttpResult(status_code=exc.code, body=body)


def validate_slack_channel_reachable(
    slack_bot_token: str,
    slack_channel_id: str,
    *,
    timeout_seconds: float = 10.0,
) -> SlackChannelCheckResult:
    """Verify a Slack channel ID is visible to the configured bot token."""
    token = slack_bot_token.strip()
    channel_id = slack_channel_id.strip()
    if not token or not channel_id:
        return SlackChannelCheckResult(False, "missing_slack_channel_credentials")

    url = "https://slack.com/api/conversations.info?" + urllib.parse.urlencode({"channel": channel_id})
    try:
        response = http_request(
            "GET",
            url,
            timeout_seconds=timeout_seconds,
            headers={"Authorization": f"Bearer {token}"},
        )
    except (OSError, urllib.error.URLError) as exc:
        return SlackChannelCheckResult(False, f"slack_request_failed:{type(exc).__name__}")

    if response.status_code != 200:
        return SlackChannelCheckResult(False, f"slack_http_{response.status_code}")
    try:
        payload = json.loads(response.body or "{}")
    except json.JSONDecodeError:
        return SlackChannelCheckResult(False, "slack_invalid_json")
    if payload.get("ok") is True and (payload.get("channel") or {}).get("id") == channel_id:
        return SlackChannelCheckResult(True, "ok")
    reason = str(payload.get("error") or "slack_channel_not_reachable")
    return SlackChannelCheckResult(False, reason)


def alert_matches(alert: dict[str, Any], config: AlertDrillConfig) -> bool:
    labels = alert.get("labels") or {}
    return labels.get("alertname") == config.alertname and labels.get("drill_id") == config.drill_id


def parse_alerts(raw_body: str) -> list[dict[str, Any]]:
    data = json.loads(raw_body or "[]")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def poll_for_alert(config: AlertDrillConfig) -> bool:
    deadline = time.monotonic() + config.timeout_seconds
    alerts_url = endpoint(
        config.alertmanager_url,
        f"/api/v2/alerts?filter={urllib.parse.quote(f'alertname={config.alertname}')}",
    )
    while time.monotonic() <= deadline:
        response = http_request("GET", alerts_url, timeout_seconds=min(config.timeout_seconds, 10.0))
        if response.status_code == 200:
            try:
                if any(alert_matches(alert, config) for alert in parse_alerts(response.body)):
                    return True
            except json.JSONDecodeError:
                pass
        time.sleep(config.poll_interval_seconds)
    return False


def build_result(
    config: AlertDrillConfig,
    *,
    ready_status_code: int,
    post_status_code: int,
    alert_visible: bool,
    slack_channel_check: SlackChannelCheckResult | None = None,
    generated_at: datetime | None = None,
) -> AlertDrillResult:
    notification_confirmed = bool(config.notification_evidence.strip())
    slack_check = slack_channel_check or SlackChannelCheckResult(False, "not_required")
    failure_reason = ""
    if config.channel_assert_reachable and not slack_check.reachable:
        failure_reason = f"slack_channel_unreachable:{slack_check.reason}"
    elif ready_status_code != 200:
        failure_reason = f"alertmanager_not_ready:{ready_status_code}"
    elif post_status_code not in {200, 202}:
        failure_reason = f"alert_post_failed:{post_status_code}"
    elif not alert_visible:
        failure_reason = "alert_not_visible"
    elif config.require_notification_evidence and not notification_confirmed:
        failure_reason = "notification_evidence_required"

    return AlertDrillResult(
        generated_at=rfc3339(generated_at or utc_now()),
        alertmanager_url=display_url(config.alertmanager_url),
        alertname=config.alertname,
        severity=config.severity,
        drill_id=config.drill_id,
        ready_status_code=ready_status_code,
        post_status_code=post_status_code,
        alert_visible=alert_visible,
        notification_delivery_confirmed=notification_confirmed,
        notification_evidence=config.notification_evidence,
        require_notification_evidence=config.require_notification_evidence,
        slack_channel_check_required=config.channel_assert_reachable,
        slack_channel_reachable=slack_check.reachable,
        slack_channel_check_reason=slack_check.reason,
        passed=not failure_reason,
        failure_reason=failure_reason,
    )


def run_drill(config: AlertDrillConfig) -> AlertDrillResult:
    slack_channel_check = SlackChannelCheckResult(False, "not_required")
    if config.channel_assert_reachable:
        slack_channel_check = validate_slack_channel_reachable(
            config.slack_bot_token,
            config.slack_channel_id,
            timeout_seconds=config.timeout_seconds,
        )
        if not slack_channel_check.reachable:
            return build_result(
                config,
                ready_status_code=0,
                post_status_code=0,
                alert_visible=False,
                slack_channel_check=slack_channel_check,
            )

    ready = http_request("GET", endpoint(config.alertmanager_url, "/-/ready"), timeout_seconds=config.timeout_seconds)
    post = HttpResult(status_code=0, body="")
    alert_visible = False
    if ready.status_code == 200:
        post = http_request(
            "POST",
            endpoint(config.alertmanager_url, "/api/v2/alerts"),
            payload=build_alert_payload(config),
            timeout_seconds=config.timeout_seconds,
        )
        if post.status_code in {200, 202}:
            alert_visible = poll_for_alert(config)

    return build_result(
        config,
        ready_status_code=ready.status_code,
        post_status_code=post.status_code,
        alert_visible=alert_visible,
        slack_channel_check=slack_channel_check,
    )


def format_human(result: AlertDrillResult) -> str:
    lines = [
        "=" * 70,
        f"DataForge Alertmanager Drill: {result.alertmanager_url}",
        f"Alert: {result.alertname} | severity={result.severity} | drill_id={result.drill_id}",
        "=" * 70,
        f"Alertmanager ready status: {result.ready_status_code}",
        f"Alert POST status:        {result.post_status_code}",
        f"Alert visible in API:     {result.alert_visible}",
        f"Notification confirmed:   {result.notification_delivery_confirmed}",
    ]
    if result.notification_evidence:
        lines.append(f"Notification evidence:    {result.notification_evidence}")
    if result.slack_channel_check_required:
        lines.append(f"Slack channel reachable:  {result.slack_channel_reachable} ({result.slack_channel_check_reason})")
    lines.extend(
        [
            "",
            "Validation Gate Status:",
            ("  [OK] Alert drill passed." if result.passed else f"  [FAIL] Alert drill failed: {result.failure_reason}"),
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post and verify a synthetic Alertmanager alert")
    parser.add_argument("--url", default=DEFAULT_ALERTMANAGER_URL, help="Alertmanager base URL")
    parser.add_argument("--alertname", default=DEFAULT_ALERTNAME, help="Synthetic alert name")
    parser.add_argument("--severity", default="info", choices=["info", "warning", "critical"], help="Alert severity")
    parser.add_argument("--drill-id", default=f"drill-{int(time.time())}", help="Unique drill id label")
    parser.add_argument("--timeout", type=float, default=30.0, help="Total wait time in seconds")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Alert API poll interval in seconds")
    parser.add_argument("--alert-duration-seconds", type=int, default=300, help="Synthetic alert duration")
    parser.add_argument("--label", action="append", default=[], help="Extra alert label, key=value")
    parser.add_argument(
        "--notification-evidence",
        default="",
        help="Slack/email/ticket evidence after a human confirms real notification delivery",
    )
    parser.add_argument(
        "--require-notification-evidence",
        action="store_true",
        help="Fail unless --notification-evidence is supplied; use for staging readiness gates",
    )
    parser.add_argument(
        "--channel-assert-reachable",
        action="store_true",
        help="Call Slack conversations.info and fail if the configured channel is not reachable by the bot token",
    )
    parser.add_argument(
        "--slack-bot-token",
        default=os.environ.get("SLACK_BOT_TOKEN", ""),
        help="Slack bot token with conversations:read scope; defaults to SLACK_BOT_TOKEN",
    )
    parser.add_argument(
        "--slack-channel-id",
        default=os.environ.get("ALERTMANAGER_SLACK_CHANNEL_ID", ""),
        help="Slack channel ID to validate; defaults to ALERTMANAGER_SLACK_CHANNEL_ID",
    )
    parser.add_argument("--json", action="store_true", help="Print only JSON to stdout")
    parser.add_argument("--json-file", type=Path, help="Write JSON result to this path")
    # F-SCRIPT-001: drill scripts that default to ``localhost`` and
    # silently retarget a remote CI runner produce false-positive
    # "drill passed" results. Operators must consciously confirm when
    # the URL points off-host. The default behaviour is a hard refusal
    # for non-localhost / non-127.0.0.1 targets unless
    # ``--allow-remote-host`` is passed OR ``DATAFORGE_DRILL_ALLOW_REMOTE=1``.
    parser.add_argument(
        "--allow-remote-host",
        action="store_true",
        help="Opt-in override that lets the drill target a non-localhost"
        " host. Required when running from a CI runner that talks to a"
        " remote Alertmanager; suppressed in default operator runs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")
    if args.poll_interval <= 0:
        parser.error("--poll-interval must be > 0")
    if args.alert_duration_seconds <= 0:
        parser.error("--alert-duration-seconds must be > 0")

    # F-SCRIPT-001 host-context confirmation. ``localhost`` and
    # ``127.0.0.1`` are in-policy without a flag; everything else
    # requires an explicit opt-out.
    env_allow = os.environ.get("DATAFORGE_DRILL_ALLOW_REMOTE") == "1"
    parsed_url = urllib.parse.urlparse(args.url)
    host_is_local = parsed_url.hostname in (None, "localhost", "127.0.0.1", "::1")
    if not host_is_local and not (args.allow_remote_host or env_allow):
        msg = (
            f"Refusing to run drill against non-localhost host "
            f"{parsed_url.hostname!r}. Re-run with --allow-remote-host"
            " (or set DATAFORGE_DRILL_ALLOW_REMOTE=1) to confirm the"
            " URL is the intended target. F-SCRIPT-001 guards against"
            " silent drills pointed at a developer's local stack from"
            " a remote CI runner."
        )
        if args.json:
            print(json.dumps({"status": "refused", "reason": msg}))
        else:
            print(f"[ERROR] {msg}")
        return 4

    labels = dict(parse_label(raw) for raw in args.label)
    config = AlertDrillConfig(
        alertmanager_url=normalize_base_url(args.url),
        alertname=args.alertname,
        severity=args.severity,
        drill_id=args.drill_id,
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.poll_interval,
        alert_duration_seconds=args.alert_duration_seconds,
        notification_evidence=args.notification_evidence,
        require_notification_evidence=args.require_notification_evidence,
        channel_assert_reachable=args.channel_assert_reachable,
        slack_bot_token=args.slack_bot_token,
        slack_channel_id=args.slack_channel_id,
        extra_labels=labels,
    )
    result = run_drill(config)
    payload = json.dumps(result.to_dict(), indent=2, sort_keys=True)
    if args.json_file:
        args.json_file.parent.mkdir(parents=True, exist_ok=True)
        args.json_file.write_text(payload + "\n", encoding="utf-8")

    if args.json:
        print(payload)
    else:
        print(format_human(result))

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
