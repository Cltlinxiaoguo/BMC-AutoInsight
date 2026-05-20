"""EventLog 路径自动探测：适配超微、戴尔 iDRAC、联想 IMM、浪潮、华为等常见实现。"""
from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, Tuple

log = logging.getLogger("bmc_autoinsight")


class JsonClient(Protocol):
    def get_json(self, path: str, optional: bool = False) -> dict: ...


def _entries_from_service(client: JsonClient, service_uri: str) -> Optional[dict[str, Any]]:
    """从单个 LogService 资源解析 Entries 集合 URI 并 GET。"""
    svc = client.get_json(service_uri, optional=True)
    if svc.get("_skipped"):
        return None
    entries_ref = svc.get("Entries")
    if isinstance(entries_ref, dict):
        eid = entries_ref.get("@odata.id")
        if eid:
            return client.get_json(eid, optional=True)
    # 常见：.../LogServices/EventLog/Entries
    cand = service_uri.rstrip("/") + "/Entries"
    r = client.get_json(cand, optional=True)
    if not r.get("_skipped"):
        return r
    return None


def discover_event_log(client: JsonClient, system_id: str) -> Tuple[dict[str, Any], str]:
    """
    返回 (entries_json 或跳过占位, 人类可读说明)。
    说明中会标注探测路径供工单与交付文档引用。
    """
    tried: list[str] = []

    # 1) 枚举 LogServices
    ls_root = f"/redfish/v1/Systems/{system_id}/LogServices"
    ls_col = client.get_json(ls_root, optional=True)
    if not ls_col.get("_skipped"):
        for m in ls_col.get("Members") or []:
            uri = m.get("@odata.id")
            if not uri:
                continue
            tried.append(uri)
            ent = _entries_from_service(client, uri)
            if ent and not ent.get("_skipped"):
                log.info("EventLog 已通过 LogServices 枚举命中: %s/Entries", uri)
                ent["_discovery_note"] = f"枚举 LogServices 成员: {uri}"
                return ent, ent["_discovery_note"]

    # 2) 厂商常见固定路径（多品牌回退）
    fallback_paths: list[str] = [
        f"/redfish/v1/Systems/{system_id}/LogServices/EventLog/Entries",
        f"/redfish/v1/Systems/{system_id}/LogServices/SEL/Entries",
        f"/redfish/v1/Systems/{system_id}/LogServices/IntegratedLog/Entries",
        # 部分华为 / 浪潮 命名
        f"/redfish/v1/Systems/{system_id}/Logs/EventLog/Entries",
    ]
    for path in fallback_paths:
        tried.append(path)
        r = client.get_json(path, optional=True)
        if not r.get("_skipped"):
            note = f"固定路径回退成功: {path}"
            log.info("EventLog %s", note)
            r["_discovery_note"] = note
            return r, note

    # 3) Managers 侧日志（少数 iDRAC 风格扩展，仅尝试）
    mgr = "/redfish/v1/Managers/1/LogServices"
    mls = client.get_json(mgr, optional=True)
    if not mls.get("_skipped"):
        for m in mls.get("Members") or []:
            uri = m.get("@odata.id")
            if not uri:
                continue
            ent = _entries_from_service(client, uri)
            if ent and not ent.get("_skipped"):
                ent["_discovery_note"] = f"Managers LogServices: {uri}"
                log.info("EventLog 通过 Managers 侧命中")
                return ent, ent["_discovery_note"]

    placeholder: dict[str, Any] = {
        "_skipped": True,
        "_status": 404,
        "_path": "event_log_discovery",
        "customer_notice_zh": (
            "【事件日志不可用】已尝试枚举 LogServices 及多品牌常见路径仍无法获取 Entries。"
            f" 已尝试路径数: {len(tried)}。请确认账号权限或厂商 OEM 文档中的日志 URI。"
        ),
        "tried_uris_sample": tried[:12],
    }
    log.warning("EventLog 全路径探测失败，已跳过。示例尝试: %s", tried[:5])
    return placeholder, placeholder["customer_notice_zh"]
