"""传感器读数展示：按 PowerState 区分 None 字段文案。"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("bmc_autoinsight")

# PowerState=Off 时 None 传感器
OFF_SENSOR_MSG = "【服务器关机，传感器无数据】"
# PowerState=On 时 None 传感器（未安装/未上报/空槽位等）
NO_REPORT_MSG = "【该传感器未上报数据】"

# Redfish PowerState 表示主机未运行或正在下电
_OFF_POWER_STATES = frozenset(
    {
        "off",
        "poweringoff",
        "paused",
        "standbyoffline",
        "standby",
        "hibernate",
        "quiesced",
    }
)


def is_server_powered_off(power_state: Optional[str]) -> bool:
    if not power_state:
        return False
    return str(power_state).strip().lower() in _OFF_POWER_STATES


def none_sensor_message(power_state: Optional[str]) -> str:
    """根据整机 PowerState 决定 None 传感器展示文案。"""
    if is_server_powered_off(power_state):
        return OFF_SENSOR_MSG
    return NO_REPORT_MSG


def format_sensor_value(value: Any, power_state: Optional[str] = None) -> Any:
    """有数值原样返回；None 则按 PowerState 选择文案。"""
    if value is not None:
        return value
    return none_sensor_message(power_state)


def is_placeholder_display(value: Any) -> bool:
    return value in (OFF_SENSOR_MSG, NO_REPORT_MSG)


def apply_sensor_display(inspection: Dict[str, Any]) -> Dict[str, Any]:
    """
    先读取 system.PowerState，再替换温度/风扇/功耗 None 字段。
    Off -> OFF_SENSOR_MSG；On/其它 -> NO_REPORT_MSG
    """
    data = copy.deepcopy(inspection)
    system = data.get("system") or {}
    power_state = system.get("PowerState")
    off = is_server_powered_off(power_state)
    placeholder = none_sensor_message(power_state)

    log.info(
        "传感器展示: PowerState=%s -> None 字段使用「%s」",
        power_state or "Unknown",
        placeholder,
    )

    thermal = data.setdefault("thermal", {})
    for temp in thermal.get("Temperatures") or []:
        if temp.get("ReadingCelsius") is None:
            temp["ReadingCelsius"] = placeholder
            temp["_display_note"] = placeholder

    for fan in thermal.get("Fans") or []:
        raw = fan.get("Reading") if fan.get("Reading") is not None else fan.get("ReadingRPM")
        if raw is None:
            fan["Reading"] = placeholder
            if "ReadingRPM" in fan:
                fan["ReadingRPM"] = placeholder

    power = data.setdefault("power", {})
    for pc in power.get("PowerControl") or []:
        if pc.get("PowerConsumedWatts") is None:
            pc["PowerConsumedWatts"] = placeholder

    for psu in power.get("PowerSupplies") or []:
        for key in ("LineInputVoltage", "LastPowerOutputWatts", "PowerCapacityWatts"):
            if psu.get(key) is None:
                psu[key] = placeholder

    notes: List[str] = list(data.get("inspection_notes") or [])
    if off:
        note = f"主机 PowerState={power_state}，None 传感器已标记为「{OFF_SENSOR_MSG}」"
    else:
        note = f"主机 PowerState={power_state}，None 传感器已标记为「{NO_REPORT_MSG}」"
    if note not in notes:
        notes.append(note)
    log.info("%s", note)

    data["inspection_notes"] = notes
    data["power_state"] = power_state
    data["host_powered_off"] = off
    data["none_sensor_placeholder"] = placeholder
    return data


def print_sensor_summary(inspection: Dict[str, Any]) -> None:
    """控制台打印传感器摘要（已按 PowerState 友好化）。"""
    data = apply_sensor_display(inspection)
    ps = data.get("power_state") or (data.get("system") or {}).get("PowerState", "Unknown")
    print(f"\n--- 传感器摘要 (PowerState={ps}) ---")
    thermal = data.get("thermal") or {}
    for temp in thermal.get("Temperatures") or []:
        name = temp.get("Name") or temp.get("MemberId") or "Temperature"
        val = temp.get("ReadingCelsius")
        health = (temp.get("Status") or {}).get("Health", "-")
        print(f"  温度 {name}: {val}  Health={health}")
    for fan in thermal.get("Fans") or []:
        name = fan.get("Name") or fan.get("MemberId") or "Fan"
        val = fan.get("Reading") or fan.get("ReadingRPM")
        print(f"  风扇 {name}: {val}")
    power = data.get("power") or {}
    for pc in power.get("PowerControl") or []:
        name = pc.get("Name") or pc.get("MemberId") or "PowerControl"
        val = pc.get("PowerConsumedWatts")
        print(f"  功耗 {name}: {val}")
    print("---\n")
