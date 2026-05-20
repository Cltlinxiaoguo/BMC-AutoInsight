"""巡检数据采集编排：动态 System/Chassis Id、超时、逐项容错。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, Protocol

from core.models import InspectionResult
from monitor import event_log, power, storage, thermal, version_info
from monitor.resolver import resolve_chassis_id, resolve_system_id

log = logging.getLogger("bmc_autoinsight")


class JsonClient(Protocol):
    def get_json(self, path: str, optional: bool = False) -> dict: ...


def _safe_collect(name: str, fn: Callable[..., dict], client: JsonClient, *args: Any) -> dict[str, Any]:
    try:
        return fn(client, *args) if args else fn(client)
    except Exception as exc:
        log.error("采集 %s 失败: %s", name, exc, exc_info=True)
        return {"_skipped": True, "_error": str(exc), "customer_notice_zh": f"模块 {name} 异常: {exc}"}


def collect_all(
    client: JsonClient,
    host: str,
    mock: bool = False,
    inspection_timeout_sec: int = 0,
    system_id_override: str | None = None,
    chassis_id_override: str | None = None,
) -> InspectionResult:
    def _run() -> InspectionResult:
        result = InspectionResult(host=host, mock=mock)
        sys_id = resolve_system_id(client, system_id_override)
        ch_id = resolve_chassis_id(client, chassis_id_override)
        result.system = _safe_collect(
            "system",
            lambda c, sid: c.get_json(f"/redfish/v1/Systems/{sid}", optional=True),
            client,
            sys_id,
        )
        result.thermal = _safe_collect("thermal", thermal.collect, client, ch_id)
        result.power = _safe_collect("power", power.collect, client, ch_id)
        result.storage = _safe_collect("storage", storage.collect, client, sys_id)
        result.event_log = _safe_collect("event_log", event_log.collect, client, sys_id)
        result.version = _safe_collect("version", version_info.collect, client)

        # 汇总客户可见提示
        for label, blob in (
            ("存储", result.storage),
            ("事件日志", result.event_log),
        ):
            notice = blob.get("customer_notice_zh") if isinstance(blob, dict) else None
            if notice:
                result.inspection_notes.append(f"{label}: {notice}")
        return result

    if inspection_timeout_sec and inspection_timeout_sec > 0:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_run)
            try:
                return fut.result(timeout=inspection_timeout_sec)
            except FuturesTimeout:
                log.error("巡检整体超时 (%ss)，已中断", inspection_timeout_sec)
                r = InspectionResult(host=host, mock=mock)
                r.inspection_notes.append(
                    f"【巡检超时】整次采集超过 {inspection_timeout_sec} 秒，已中止。请增大 basic.inspection_timeout 或检查网络。"
                )
                r.system = {"_skipped": True, "_error": "inspection_timeout"}
                return r

    return _run()
