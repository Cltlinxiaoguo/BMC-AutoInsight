"""解析 Redfish 中 System / Chassis 资源 Id（兼容多厂商实例命名）。"""
from __future__ import annotations

import logging
from typing import Any, Protocol

log = logging.getLogger("bmc_autoinsight")


class JsonClient(Protocol):
    def get_json(self, path: str, optional: bool = False) -> dict: ...


def _first_member_id(collection: dict[str, Any], default: str) -> str:
    members = collection.get("Members") or []
    if not members:
        return default
    oid = (members[0] or {}).get("@odata.id") or ""
    if not oid:
        return default
    return oid.rstrip("/").split("/")[-1] or default


def resolve_system_id(client: JsonClient, override: str | None = None) -> str:
    if override:
        return override
    col = client.get_json("/redfish/v1/Systems", optional=True)
    if col.get("_skipped"):
        log.warning("无法枚举 Systems，使用默认 system_id=1")
        return "1"
    sid = _first_member_id(col, "1")
    log.info("解析 System Id=%s", sid)
    return sid


def resolve_manager_id(client: JsonClient, override: str | None = None) -> str:
    if override:
        return override
    col = client.get_json("/redfish/v1/Managers", optional=True)
    if col.get("_skipped"):
        log.warning("无法枚举 Managers，使用默认 manager_id=1")
        return "1"
    mid = _first_member_id(col, "1")
    log.info("解析 Manager Id=%s", mid)
    return mid


def resolve_chassis_id(client: JsonClient, override: str | None = None) -> str:
    if override:
        return override
    col = client.get_json("/redfish/v1/Chassis", optional=True)
    if col.get("_skipped"):
        log.warning("无法枚举 Chassis，使用默认 chassis_id=1")
        return "1"
    cid = _first_member_id(col, "1")
    log.info("解析 Chassis Id=%s", cid)
    return cid
