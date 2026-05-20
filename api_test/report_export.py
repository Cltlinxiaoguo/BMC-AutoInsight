"""API 冒烟报告导出。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from reports.exporter import _timestamp


def _api_only_html(summary: Dict[str, Any], host: str = "") -> str:
    rows = summary.get("cases") or []
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    total = summary.get("total", len(rows))
    ts = datetime.now().isoformat(timespec="seconds")

    body_rows = []
    for a in rows:
        cls = "ok" if a.get("passed") else "err"
        body_rows.append(
            f'<tr class="{cls}"><td>{a.get("name")}</td><td>{a.get("path")}</td>'
            f'<td>{a.get("status")}</td><td>{a.get("duration_ms")}</td>'
            f'<td>{"PASS" if a.get("passed") else "FAIL"}</td></tr>'
        )

    table = "\n".join(body_rows)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>API 冒烟报告</title>
<style>
body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ccc;padding:8px}}
th{{background:#e3f2fd}} .ok{{background:#e8f5e9}} .err{{background:#ffebee;color:#c62828}}
</style></head><body>
<h1>BMC AutoInsight — API 冒烟报告</h1>
<p>目标: {host} | 时间: {ts} | 总计 {total} / 通过 {passed} / 失败 {failed}</p>
<h2>API 冒烟</h2>
<table>
<tr><th>用例</th><th>路径</th><th>HTTP</th><th>耗时ms</th><th>结果</th></tr>
{table}
</table>
</body></html>"""


def export_api_smoke_bundle(
    report_dir: Path,
    summary: Dict[str, Any],
    *,
    host: str = "",
    prefix: str = "api_smoke",
) -> Dict[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    payload = {"host": host, "timestamp": datetime.now().isoformat(), **summary}
    json_path = report_dir / f"{prefix}_{ts}.json"
    html_path = report_dir / f"{prefix}_{ts}.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_api_only_html(summary, host=host), encoding="utf-8")
    return {"json": str(json_path), "html": str(html_path)}
