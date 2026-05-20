"""Mock Redfish 客户端，从 fixtures 加载。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.exceptions import MockFixtureError


class MockRedfishClient:
    PATH_MAP = {
        "/redfish/v1/": "service_root.json",
        "/redfish/v1/SessionService/Sessions": "session.json",
        "/redfish/v1/SessionService": "session_service.json",
        "/redfish/v1/Systems": "systems.json",
        "/redfish/v1/Systems/1": "system.json",
        "/redfish/v1/Chassis": "chassis_collection.json",
        "/redfish/v1/Chassis/1": "chassis.json",
        "/redfish/v1/Chassis/1/Thermal": "thermal.json",
        "/redfish/v1/Chassis/1/Power": "power.json",
        "/redfish/v1/Managers": "managers.json",
        "/redfish/v1/Managers/1": "manager.json",
        "/redfish/v1/Systems/1/Processors": "processors.json",
        "/redfish/v1/Systems/1/Processors/1": "processor.json",
        "/redfish/v1/Systems/1/Memory": "memory_collection.json",
        "/redfish/v1/Systems/1/Memory/1": "memory_module.json",
        "/redfish/v1/Systems/1/Storage/RAID1": "storage_raid.json",
        "/redfish/v1/Chassis/1/Drives/Disk1": "drive.json",
        "/redfish/v1/Systems/1/Storage": "storage.json",
        "/redfish/v1/Systems/1/LogServices/EventLog/Entries": "event_log.json",
    }

    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir

    def _load(self, name: str) -> Dict[str, Any]:
        p = self.fixture_dir / name
        if not p.exists():
            raise MockFixtureError(f"缺少 fixture: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def get_json(self, path: str, optional: bool = False) -> Dict[str, Any]:
        norm = path if path.startswith("/") else "/" + path
        if norm.endswith("/") and norm != "/redfish/v1/":
            norm = norm.rstrip("/")
        fname = self.PATH_MAP.get(norm)
        if fname is None:
            if optional:
                return {"_skipped": True, "_status": 404, "_path": path}
            raise MockFixtureError(f"未映射 Mock 路径: {norm}")
        try:
            return self._load(fname)
        except MockFixtureError:
            if optional:
                return {"_skipped": True, "_status": 404, "_path": path}
            raise

    def request(self, method: str, path: str, **kwargs):
        body = self.get_json(path, optional=True)

        class _Resp:
            def __init__(self, data):
                self._data = data
                if isinstance(data, dict) and data.get("_skipped"):
                    self.status_code = int(data.get("_status") or 404)
                else:
                    self.status_code = 200

            def json(self):
                return self._data

            @property
            def text(self):
                return "{}"

        return _Resp(body)
