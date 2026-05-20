"""报告导出：API 冒烟表格非空。"""
from pathlib import Path

from reports.exporter import _prepare_api_rows, export_html


def test_prepare_api_rows_empty_has_placeholder():
    rows = _prepare_api_rows([])
    assert len(rows) == 1
    assert "未执行" in rows[0]["name"]


def test_export_html_api_smoke_not_blank(tmp_path):
    payload = {
        "host": "demo",
        "timestamp": "2026-01-01T00:00:00",
        "api_test": [
            {"name": "root", "path": "/redfish/v1/", "status": 200, "duration_ms": 1.2, "passed": True},
            {"name": "bad", "path": "/x", "status": 403, "duration_ms": 2.0, "passed": False},
        ],
    }
    html_path = export_html(tmp_path, payload, prefix="test")
    text = html_path.read_text(encoding="utf-8")
    assert "API 冒烟" in text
    assert "/redfish/v1/" in text
    assert "PASS" in text
    assert "FAIL" in text
    assert "{%" not in text
