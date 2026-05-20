"""硬件信息与固件版本采集（Redfish Systems / Managers / Chassis / Storage）。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from monitor.resolver import resolve_chassis_id, resolve_manager_id, resolve_system_id

log = logging.getLogger("bmc_autoinsight")


def _deep_get(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _bytes_to_gib(n: Any) -> Optional[float]:
    try:
        val = float(n)
    except (TypeError, ValueError):
        return None
    return round(val / (1024**3), 2)


def _member_links(collection: dict) -> List[str]:
    links: List[str] = []
    for item in collection.get("Members") or []:
        if isinstance(item, dict):
            oid = item.get("@odata.id")
            if isinstance(oid, str):
                links.append(oid)
    return links


def _bios_version(system: dict) -> str:
    for path in (
        ("BiosVersion",),
        ("Oem", "Supermicro", "BIOSVersion"),
        ("Oem", "Supermicro", "BiosVersion"),
        ("Oem", "Dell", "BiosVersion"),
        ("Oem", "Hpe", "Bios", "Current", "VersionString"),
    ):
        val = _deep_get(system, *path)
        if val:
            return str(val)
    return ""


def _collect_cpus(client: Any, system: dict, sys_id: str) -> List[Dict[str, Any]]:
    proc_col = client.get_json(f"/redfish/v1/Systems/{sys_id}/Processors", optional=True)
    cpus: List[Dict[str, Any]] = []
    if not proc_col.get("_skipped") and _member_links(proc_col):
        for link in _member_links(proc_col):
            proc = client.get_json(link, optional=True)
            if proc.get("_skipped"):
                continue
            cpus.append(
                {
                    "id": proc.get("Id") or link.rsplit("/", 1)[-1],
                    "model": proc.get("Model") or proc.get("ProcessorType") or "",
                    "count": 1,
                    "cores": proc.get("TotalCores") or proc.get("CoreCount"),
                    "threads": proc.get("TotalThreads") or proc.get("LogicalProcessorCount"),
                    "speed_mhz": proc.get("MaxSpeedMHz") or proc.get("OperatingSpeedMHz"),
                    "manufacturer": proc.get("Manufacturer") or "",
                }
            )
        return cpus

    summary = system.get("ProcessorSummary") or {}
    if summary:
        cpus.append(
            {
                "id": "summary",
                "model": summary.get("Model") or "",
                "count": summary.get("Count"),
                "cores": summary.get("CoreCount") or summary.get("Count"),
                "threads": summary.get("LogicalProcessorCount"),
                "speed_mhz": summary.get("SpeedMHz"),
                "manufacturer": summary.get("Manufacturer") or system.get("Manufacturer") or "",
            }
        )
    return cpus


def _memory_total_gib(summary: dict) -> Optional[float]:
    gib = summary.get("TotalSystemMemoryGiB")
    if isinstance(gib, (int, float)):
        return round(float(gib), 2)
    return _bytes_to_gib(summary.get("TotalSystemMemoryBytes"))


def _collect_memory(client: Any, system: dict, sys_id: str) -> Dict[str, Any]:
    summary = system.get("MemorySummary") or {}
    out: Dict[str, Any] = {
        "total_gib": _memory_total_gib(summary),
        "modules": [],
    }

    mem_col = client.get_json(f"/redfish/v1/Systems/{sys_id}/Memory", optional=True)
    if mem_col.get("_skipped"):
        return out

    for link in _member_links(mem_col):
        mod = client.get_json(link, optional=True)
        if mod.get("_skipped"):
            continue
        cap = mod.get("CapacityMiB")
        cap_gib = round(float(cap) / 1024, 2) if cap else _bytes_to_gib(mod.get("CapacityBytes"))
        out["modules"].append(
            {
                "id": mod.get("Id") or link.rsplit("/", 1)[-1],
                "capacity_gib": cap_gib,
                "type": mod.get("MemoryDeviceType") or mod.get("MemoryType") or "",
                "speed_mhz": mod.get("OperatingSpeedMhz") or mod.get("AllowedSpeedsMHz"),
                "manufacturer": mod.get("Manufacturer") or "",
                "serial": mod.get("SerialNumber") or "",
                "part_number": mod.get("PartNumber") or "",
            }
        )
    return out


def _collect_disks(client: Any, storage: dict) -> List[Dict[str, Any]]:
    disks: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add_drive(drive: dict) -> None:
        oid = drive.get("@odata.id") or drive.get("Id") or ""
        key = str(oid)
        if key in seen:
            return
        seen.add(key)
        cap = drive.get("CapacityBytes")
        disks.append(
            {
                "id": drive.get("Id") or key.rsplit("/", 1)[-1],
                "model": drive.get("Model") or drive.get("Name") or "",
                "capacity_gib": _bytes_to_gib(cap),
                "protocol": drive.get("Protocol") or "",
                "media_type": drive.get("MediaType") or "",
                "health": _deep_get(drive, "Status", "Health") or "",
                "serial": drive.get("SerialNumber") or "",
            }
        )

    for link in _member_links(storage):
        ctrl = client.get_json(link, optional=True)
        if ctrl.get("_skipped"):
            continue
        for d in ctrl.get("Drives") or []:
            if isinstance(d, dict) and d.get("@odata.id"):
                detail = client.get_json(d["@odata.id"], optional=True)
                if not detail.get("_skipped"):
                    _add_drive(detail)
            elif isinstance(d, dict):
                _add_drive(d)

    for d in storage.get("Drives") or []:
        if isinstance(d, dict) and d.get("@odata.id"):
            detail = client.get_json(d["@odata.id"], optional=True)
            if not detail.get("_skipped"):
                _add_drive(detail)
        elif isinstance(d, dict):
            _add_drive(d)

    return disks


def collect_hardware_info(
    client: Any,
    *,
    system_id_override: str | None = None,
    chassis_id_override: str | None = None,
    manager_id_override: str | None = None,
) -> Dict[str, Any]:
    """采集服务器硬件与固件信息。"""
    sys_id = resolve_system_id(client, system_id_override)
    ch_id = resolve_chassis_id(client, chassis_id_override)
    mgr_id = resolve_manager_id(client, manager_id_override)

    system = client.get_json(f"/redfish/v1/Systems/{sys_id}", optional=True)
    chassis = client.get_json(f"/redfish/v1/Chassis/{ch_id}", optional=True)
    manager = client.get_json(f"/redfish/v1/Managers/{mgr_id}", optional=True)
    storage = client.get_json(f"/redfish/v1/Systems/{sys_id}/Storage", optional=True)

    motherboard = {
        "part_number": chassis.get("PartNumber") or system.get("PartNumber") or "",
        "serial_number": chassis.get("SerialNumber") or system.get("SerialNumber") or "",
        "model": chassis.get("Model") or system.get("Model") or "",
        "manufacturer": chassis.get("Manufacturer") or system.get("Manufacturer") or "",
        "sku": chassis.get("SKU") or system.get("SKU") or "",
    }

    info: Dict[str, Any] = {
        "system_id": sys_id,
        "chassis_id": ch_id,
        "manager_id": mgr_id,
        "summary": {
            "model": system.get("Model") or "",
            "serial_number": system.get("SerialNumber") or "",
            "manufacturer": system.get("Manufacturer") or "",
            "bios_version": _bios_version(system),
            "bmc_firmware_version": manager.get("FirmwareVersion") or "",
            "power_state": system.get("PowerState") or "",
            "host_name": system.get("HostName") or manager.get("HostName") or "",
        },
        "cpu": _collect_cpus(client, system, sys_id),
        "memory": _collect_memory(client, system, sys_id),
        "disks": _collect_disks(client, storage) if not storage.get("_skipped") else [],
        "motherboard": motherboard,
        "storage_notice": storage.get("customer_notice_zh") or "",
    }
    if storage.get("_skipped") and storage.get("_status") == 403:
        info["storage_notice"] = storage.get("customer_notice_zh") or "存储模块权限受限，硬盘详情可能不完整"
    log.info(
        "硬件信息: %s %s BIOS=%s BMC=%s",
        info["summary"].get("manufacturer"),
        info["summary"].get("model"),
        info["summary"].get("bios_version"),
        info["summary"].get("bmc_firmware_version"),
    )
    return info


def print_hardware_info(info: Dict[str, Any]) -> None:
    """控制台输出硬件信息。"""
    s = info.get("summary") or {}
    mb = info.get("motherboard") or {}
    print("\n" + "=" * 60)
    print("硬件信息与固件版本")
    print("=" * 60)
    print(f"  制造商      : {s.get('manufacturer')}")
    print(f"  型号        : {s.get('model')}")
    print(f"  序列号      : {s.get('serial_number')}")
    print(f"  主机名      : {s.get('host_name')}")
    print(f"  PowerState  : {s.get('power_state')}")
    print(f"  BIOS 版本   : {s.get('bios_version')}")
    print(f"  BMC 固件    : {s.get('bmc_firmware_version')}")
    print("-" * 60)
    print("  主板信息")
    print(f"    制造商    : {mb.get('manufacturer')}")
    print(f"    型号      : {mb.get('model')}")
    print(f"    部件号    : {mb.get('part_number')}")
    print(f"    序列号    : {mb.get('serial_number')}")
    print(f"    SKU       : {mb.get('sku')}")
    print("-" * 60)
    print("  CPU")
    for cpu in info.get("cpu") or []:
        print(
            f"    [{cpu.get('id')}] {cpu.get('manufacturer')} {cpu.get('model')} "
            f"核={cpu.get('cores')} 线程={cpu.get('threads')} {cpu.get('speed_mhz')}MHz"
        )
    if not info.get("cpu"):
        print("    (无 CPU 详情)")
    print("-" * 60)
    mem = info.get("memory") or {}
    print(f"  内存总量    : {mem.get('total_gib') or '-'} GiB")
    for mod in mem.get("modules") or []:
        print(
            f"    [{mod.get('id')}] {mod.get('capacity_gib')}GiB {mod.get('type')} "
            f"{mod.get('speed_mhz')}MHz {mod.get('manufacturer')} SN={mod.get('serial')}"
        )
    if not mem.get("modules"):
        print("    (无内存条详情)")
    print("-" * 60)
    print("  硬盘")
    for disk in info.get("disks") or []:
        print(
            f"    [{disk.get('id')}] {disk.get('model')} {disk.get('capacity_gib')}GiB "
            f"{disk.get('protocol')} {disk.get('media_type')} Health={disk.get('health')}"
        )
    if not info.get("disks"):
        notice = info.get("storage_notice")
        print(f"    (无硬盘详情{(' — ' + notice) if notice else ''})")
    print("=" * 60 + "\n")
