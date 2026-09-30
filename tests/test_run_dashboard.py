from __future__ import annotations

from datetime import datetime, timezone

from scripts.run_dashboard import HTML_TEMPLATE, filter_recent_records


def test_filter_recent_records_keeps_only_last_60_minutes() -> None:
    now = datetime(2026, 9, 30, 5, 0, tzinfo=timezone.utc)
    records = [
        {"ts": "2026-09-30T03:59:59Z", "event": "request_received"},
        {"ts": "2026-09-30T04:00:00Z", "event": "request_received"},
        {"ts": "2026-09-30T04:30:00Z", "event": "response_sent"},
        {"ts": "invalid", "event": "request_failed"},
    ]

    filtered = filter_recent_records(records, now=now)

    assert [record["ts"] for record in filtered] == [
        "2026-09-30T04:00:00Z",
        "2026-09-30T04:30:00Z",
    ]


def test_dashboard_template_renders_total_cost_value() -> None:
    html = HTML_TEMPLATE.format(
        generated_at="2026-09-30 12:00:00",
        total_requests=10,
        global_p95=250,
        global_error_rate=0,
        total_cost_usd=0.123456,
        global_quality=0.8,
        data_json="{}",
    )

    assert "$0.123456" in html
    assert "${total_cost_usd}" not in html

