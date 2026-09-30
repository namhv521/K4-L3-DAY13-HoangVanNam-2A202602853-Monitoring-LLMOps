"""
scripts/run_dashboard.py
Đọc data/logs.jsonl, tính toán metrics và xuất dashboard HTML 6 panel.
Chạy: python scripts/run_dashboard.py
Mở: submission/evidence/dashboard.html trong trình duyệt để chụp ảnh evidence.
Không cần cài thêm package — chỉ dùng stdlib + Chart.js từ CDN.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

LOG_PATH = Path("data/logs.jsonl")
OUT_PATH = Path("submission/evidence/dashboard.html")


# ── Đọc logs ──────────────────────────────────────────────────────────────────

def read_logs() -> list[dict]:
    if not LOG_PATH.exists():
        print(f"[WARN] {LOG_PATH} không tồn tại. Chạy load_test.py trước.")
        return []
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def filter_recent_records(
    records: list[dict],
    *,
    now: datetime | None = None,
    minutes: int = 60,
) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(minutes=minutes)
    recent = []
    for record in records:
        try:
            timestamp = datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        if cutoff <= timestamp <= current:
            recent.append(record)
    return recent


def to_minute(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except Exception:
        return "??"


def pct(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = min(int(len(s) * p / 100), len(s) - 1)
    return round(s[idx], 2)


# ── Tính toán ─────────────────────────────────────────────────────────────────

def compute(records: list[dict]) -> dict:
    resp = [r for r in records if r.get("event") == "response_sent"]
    recv = [r for r in records if r.get("event") == "request_received"]
    fail = [r for r in records if r.get("event") == "request_failed"]
    # retrieval success: lấy TẤT CẢ record có field tool_success (bao gồm response_sent lẫn request_failed)
    with_tool = [r for r in records if r.get("tool_success") is not None]

    lat_m: dict[str, list] = defaultdict(list)
    ttft_m: dict[str, list] = defaultdict(list)
    traffic_m: dict[str, int] = defaultdict(int)
    err_m: dict[str, int] = defaultdict(int)
    total_m: dict[str, int] = defaultdict(int)
    ret_m: dict[str, list] = defaultdict(list)
    cost_m: dict[str, float] = defaultdict(float)
    tin_m: dict[str, int] = defaultdict(int)
    tout_m: dict[str, int] = defaultdict(int)
    qual_m: dict[str, list] = defaultdict(list)

    for r in resp:
        m = to_minute(r.get("ts", ""))
        if r.get("latency_ms") is not None:
            lat_m[m].append(r["latency_ms"])
        if r.get("ttft_ms") is not None:
            ttft_m[m].append(r["ttft_ms"])
        cost_m[m] += r.get("cost_usd", 0)
        tin_m[m] += r.get("tokens_in", 0)
        tout_m[m] += r.get("tokens_out", 0)
        if r.get("quality_score") is not None:
            qual_m[m].append(r["quality_score"])

    for r in recv:
        m = to_minute(r.get("ts", ""))
        traffic_m[m] += 1
        total_m[m] += 1

    for r in fail:
        m = to_minute(r.get("ts", ""))
        err_m[m] += 1

    for r in with_tool:
        m = to_minute(r.get("ts", ""))
        ret_m[m].append(1 if r["tool_success"] else 0)

    minutes = sorted(set(
        list(lat_m) + list(traffic_m) + list(cost_m) + list(qual_m)
    ))

    all_lat = [v for vals in lat_m.values() for v in vals]
    all_ttft = [v for vals in ttft_m.values() for v in vals]

    def safe_mean(lst: list) -> float:
        return round(sum(lst) / len(lst), 3) if lst else 0.0

    return {
        "minutes": minutes,
        "latency": {
            "p50": [pct(lat_m.get(m, []), 50) for m in minutes],
            "p95": [pct(lat_m.get(m, []), 95) for m in minutes],
            "p99": [pct(lat_m.get(m, []), 99) for m in minutes],
            "ttft_p95": [pct(ttft_m.get(m, []), 95) for m in minutes],
            "global_p50": pct(all_lat, 50),
            "global_p95": pct(all_lat, 95),
            "global_p99": pct(all_lat, 99),
            "global_ttft_p95": pct(all_ttft, 95),
            "threshold": 3000,
        },
        "traffic": {
            "by_minute": [traffic_m.get(m, 0) for m in minutes],
            "total": len(recv),
            "threshold": 1,
        },
        "errors": {
            "error_rate": [
                round(err_m.get(m, 0) / max(total_m.get(m, 1), 1) * 100, 1)
                for m in minutes
            ],
            "retrieval_success": [
                round(sum(ret_m.get(m, [0])) / max(len(ret_m.get(m, [1])), 1) * 100, 1)
                for m in minutes
            ],
            "global_error_rate": round(len(fail) / max(len(recv), 1) * 100, 1),
            "total_errors": len(fail),
            "error_threshold": 2,
            "retrieval_threshold": 90,
        },
        "cost": {
            "by_minute": [round(cost_m.get(m, 0), 6) for m in minutes],
            "total": round(sum(cost_m.values()), 6),
            "threshold": 2.5,
        },
        "tokens": {
            "in": [tin_m.get(m, 0) for m in minutes],
            "out": [tout_m.get(m, 0) for m in minutes],
            "threshold": 50000,
        },
        "quality": {
            "by_minute": [
                safe_mean(qual_m.get(m, [])) for m in minutes
            ],
            "global_mean": safe_mean([r.get("quality_score", 0) for r in resp]),
            "threshold": 0.75,
        },
        "summary": {
            "total_requests": len(recv),
            "total_errors": len(fail),
            "total_cost_usd": round(sum(cost_m.values()), 6),
        },
    }


# ── HTML Template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>K4-L3B Day 13 — Monitoring Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; padding: 16px; }}
  h1 {{ text-align: center; color: #7eb8f7; margin-bottom: 4px; font-size: 1.4rem; }}
  .meta {{ text-align: center; color: #888; font-size: 0.8rem; margin-bottom: 16px; }}
  .summary {{ display: flex; gap: 12px; justify-content: center; margin-bottom: 16px; flex-wrap: wrap; }}
  .kpi {{ background: #1a1d27; border: 1px solid #333; border-radius: 8px; padding: 10px 20px; text-align: center; }}
  .kpi .val {{ font-size: 1.6rem; font-weight: bold; color: #7eb8f7; }}
  .kpi .lbl {{ font-size: 0.75rem; color: #888; margin-top: 2px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }}
  .panel {{ background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 10px; padding: 14px; }}
  .panel h2 {{ font-size: 0.85rem; color: #aaa; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .panel .subtitle {{ font-size: 0.72rem; color: #666; margin-bottom: 10px; }}
  canvas {{ max-height: 200px; }}
  @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} }}
  @media (max-width: 600px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>🔭 K4-L3B Day 13 — Monitoring &amp; LLMOps Dashboard</h1>
<p class="meta">Source: data/logs.jsonl &nbsp;|&nbsp; Time range: 60 min &nbsp;|&nbsp; Generated: {generated_at}</p>

<div class="summary">
  <div class="kpi"><div class="val">{total_requests}</div><div class="lbl">Total Requests</div></div>
  <div class="kpi"><div class="val">{global_p95} ms</div><div class="lbl">Latency P95</div></div>
  <div class="kpi"><div class="val">{global_error_rate}%</div><div class="lbl">Error Rate</div></div>
  <div class="kpi"><div class="val">${total_cost_usd}</div><div class="lbl">Total Cost (USD)</div></div>
  <div class="kpi"><div class="val">{global_quality}</div><div class="lbl">Avg Quality Score</div></div>
</div>

<div class="grid">

  <!-- Panel 1: Latency -->
  <div class="panel">
    <h2>⏱ Latency Percentiles &amp; TTFT</h2>
    <p class="subtitle">P50 / P95 / P99 / TTFT-P95 (ms) — threshold 3000 ms</p>
    <canvas id="latencyChart"></canvas>
  </div>

  <!-- Panel 2: Traffic -->
  <div class="panel">
    <h2>📈 Request Traffic</h2>
    <p class="subtitle">Requests per minute — threshold ≥ 1 rpm</p>
    <canvas id="trafficChart"></canvas>
  </div>

  <!-- Panel 3: Errors + Retrieval Success -->
  <div class="panel">
    <h2>🚨 Error Rate &amp; Retrieval Success</h2>
    <p class="subtitle">Error rate % (threshold ≤ 2%) | Retrieval success % (threshold ≥ 90%)</p>
    <canvas id="errorsChart"></canvas>
  </div>

  <!-- Panel 4: Cost -->
  <div class="panel">
    <h2>💰 Cost Over Time</h2>
    <p class="subtitle">USD per minute — total threshold ≤ $2.50</p>
    <canvas id="costChart"></canvas>
  </div>

  <!-- Panel 5: Tokens -->
  <div class="panel">
    <h2>🔤 Input &amp; Output Tokens</h2>
    <p class="subtitle">Tokens per minute — threshold ≤ 50,000</p>
    <canvas id="tokensChart"></canvas>
  </div>

  <!-- Panel 6: Quality -->
  <div class="panel">
    <h2>⭐ Quality Proxy Score</h2>
    <p class="subtitle">Mean quality score per minute — threshold ≥ 0.75</p>
    <canvas id="qualityChart"></canvas>
  </div>

</div>

<script>
const DATA = {data_json};

const COLORS = {{
  p50:  '#4ade80', p95: '#facc15', p99: '#f87171',
  ttft: '#818cf8', traffic: '#38bdf8',
  error: '#f87171', retrieval: '#4ade80',
  cost: '#fb923c', tin: '#60a5fa', tout: '#c084fc',
  quality: '#34d399',
}};

function thresholdLine(value, label, color='#f87171') {{
  return {{
    type: 'line',
    data: Array(DATA.minutes.length).fill(value),
    label: label,
    borderColor: color,
    borderDash: [6,3],
    borderWidth: 1.5,
    pointRadius: 0,
    fill: false,
  }};
}}

const baseOpts = {{
  responsive: true,
  maintainAspectRatio: true,
  plugins: {{ legend: {{ labels: {{ color: '#ccc', font: {{ size: 10 }} }} }} }},
  scales: {{
    x: {{ ticks: {{ color: '#888', font: {{ size: 9 }} }}, grid: {{ color: '#2a2d3a' }} }},
    y: {{ ticks: {{ color: '#888', font: {{ size: 9 }} }}, grid: {{ color: '#2a2d3a' }} }},
  }},
}};

// Panel 1: Latency
new Chart(document.getElementById('latencyChart'), {{
  type: 'line',
  data: {{
    labels: DATA.minutes,
    datasets: [
      {{ label: 'P50 (ms)', data: DATA.latency.p50, borderColor: COLORS.p50, tension: 0.3, pointRadius: 2, fill: false }},
      {{ label: 'P95 (ms)', data: DATA.latency.p95, borderColor: COLORS.p95, tension: 0.3, pointRadius: 2, fill: false }},
      {{ label: 'P99 (ms)', data: DATA.latency.p99, borderColor: COLORS.p99, tension: 0.3, pointRadius: 2, fill: false }},
      {{ label: 'TTFT P95', data: DATA.latency.ttft_p95, borderColor: COLORS.ttft, tension: 0.3, pointRadius: 2, fill: false, borderDash: [4,2] }},
      thresholdLine(DATA.latency.threshold, 'SLO 3000ms'),
    ],
  }},
  options: {{ ...baseOpts, plugins: {{ ...baseOpts.plugins, tooltip: {{ mode: 'index' }} }} }},
}});

// Panel 2: Traffic
new Chart(document.getElementById('trafficChart'), {{
  type: 'bar',
  data: {{
    labels: DATA.minutes,
    datasets: [
      {{ label: 'Requests/min', data: DATA.traffic.by_minute, backgroundColor: COLORS.traffic + 'aa', borderColor: COLORS.traffic, borderWidth: 1 }},
      thresholdLine(DATA.traffic.threshold, 'Min threshold'),
    ],
  }},
  options: baseOpts,
}});

// Panel 3: Errors
new Chart(document.getElementById('errorsChart'), {{
  type: 'line',
  data: {{
    labels: DATA.minutes,
    datasets: [
      {{ label: 'Error Rate %', data: DATA.errors.error_rate, borderColor: COLORS.error, tension: 0.3, pointRadius: 2, fill: false }},
      {{ label: 'Retrieval Success %', data: DATA.errors.retrieval_success, borderColor: COLORS.retrieval, tension: 0.3, pointRadius: 2, fill: false }},
      thresholdLine(DATA.errors.error_threshold, 'Error ≤ 2%'),
      thresholdLine(DATA.errors.retrieval_threshold, 'Retrieval ≥ 90%', '#4ade80'),
    ],
  }},
  options: baseOpts,
}});

// Panel 4: Cost
new Chart(document.getElementById('costChart'), {{
  type: 'line',
  data: {{
    labels: DATA.minutes,
    datasets: [
      {{ label: 'Cost USD/min', data: DATA.cost.by_minute, borderColor: COLORS.cost, tension: 0.3, pointRadius: 2, fill: true, backgroundColor: COLORS.cost + '22' }},
      thresholdLine(DATA.cost.threshold / DATA.minutes.length || 0.001, 'Budget/min'),
    ],
  }},
  options: baseOpts,
}});

// Panel 5: Tokens
new Chart(document.getElementById('tokensChart'), {{
  type: 'bar',
  data: {{
    labels: DATA.minutes,
    datasets: [
      {{ label: 'Input tokens', data: DATA.tokens.in, backgroundColor: COLORS.tin + 'aa', borderColor: COLORS.tin, borderWidth: 1 }},
      {{ label: 'Output tokens', data: DATA.tokens.out, backgroundColor: COLORS.tout + 'aa', borderColor: COLORS.tout, borderWidth: 1 }},
    ],
  }},
  options: {{ ...baseOpts, scales: {{ ...baseOpts.scales, x: {{ ...baseOpts.scales.x, stacked: true }}, y: {{ ...baseOpts.scales.y, stacked: true }} }} }},
}});

// Panel 6: Quality
new Chart(document.getElementById('qualityChart'), {{
  type: 'line',
  data: {{
    labels: DATA.minutes,
    datasets: [
      {{ label: 'Quality Score', data: DATA.quality.by_minute, borderColor: COLORS.quality, tension: 0.3, pointRadius: 2, fill: true, backgroundColor: COLORS.quality + '22' }},
      thresholdLine(DATA.quality.threshold, 'Min 0.75', '#4ade80'),
    ],
  }},
  options: {{ ...baseOpts, scales: {{ ...baseOpts.scales, y: {{ ...baseOpts.scales.y, min: 0, max: 1 }} }} }},
}});
</script>
</body>
</html>
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    configure_utf8_stdio()
    records = filter_recent_records(read_logs())
    print(f"[INFO] Đọc được {len(records)} dòng log trong 60 phút từ {LOG_PATH}")

    data = compute(records)

    if not data["minutes"]:
        print("[WARN] Không có dữ liệu để vẽ. Đảm bảo API đang chạy và đã chạy load_test.py")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = HTML_TEMPLATE.format(
        generated_at=generated_at,
        total_requests=data["summary"]["total_requests"],
        global_p95=data["latency"]["global_p95"],
        global_error_rate=data["errors"]["global_error_rate"],
        total_cost_usd=data["summary"]["total_cost_usd"],
        global_quality=data["quality"]["global_mean"],
        data_json=json.dumps(data, ensure_ascii=False),
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"[OK] Dashboard xuất ra: {OUT_PATH}")
    print(f"     Mở file trong trình duyệt → chụp ảnh → lưu vào submission/evidence/11-dashboard-overview.png")
    print()
    print("=== Tóm tắt ===")
    print(f"  Tổng requests : {data['summary']['total_requests']}")
    print(f"  Latency P50/P95/P99 : {data['latency']['global_p50']} / {data['latency']['global_p95']} / {data['latency']['global_p99']} ms")
    print(f"  TTFT P95      : {data['latency']['global_ttft_p95']} ms")
    print(f"  Error rate    : {data['errors']['global_error_rate']}%")
    print(f"  Total cost    : ${data['summary']['total_cost_usd']}")
    print(f"  Quality mean  : {data['quality']['global_mean']}")


if __name__ == "__main__":
    main()
