"""事件日志：多路径自动探测。"""
from __future__ import annotations

from monitor.event_discovery import discover_event_log


def collect(client, system_id: str = "1") -> dict:
    data, summary = discover_event_log(client, system_id)
    data["_event_log_probe_summary"] = summary
    return data
