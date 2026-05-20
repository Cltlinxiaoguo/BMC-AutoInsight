"""故障检测引擎：温度/风扇/功耗阈值来自 config。"""
from __future__ import annotations

from typing import Any, Dict, List

from fault_detect.rules import ALL_RULES


def run_fault_checks(snapshot: Dict[str, Any], thresholds: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for mod in ALL_RULES:
        try:
            findings.extend(mod.check(snapshot, thresholds))
        except Exception as exc:
            findings.append(
                {"rule": "engine", "severity": "warn", "message": f"规则 {getattr(mod, '__name__', mod)} 异常: {exc}"}
            )

    # 温度：CPU/入口传感器
    tcfg = thresholds.get("thermal") or {}
    warn = float(tcfg.get("cpu_temp_warn_c", 75))
    crit = float(tcfg.get("cpu_temp_crit_c", 85))
    for temp in (snapshot.get("thermal") or {}).get("Temperatures") or []:
        val = temp.get("ReadingCelsius")
        if val is None:
            continue
        name = temp.get("Name") or temp.get("MemberId") or "sensor"
        if val >= crit:
            findings.append(
                {"rule": "thermal", "severity": "crit", "message": f"{name} 温度超上限({crit}°C): {val}°C"}
            )
        elif val >= warn:
            findings.append(
                {"rule": "thermal", "severity": "warn", "message": f"{name} 温度超预警({warn}°C): {val}°C"}
            )

    # 功耗：PowerControl PowerConsumedWatts
    pcfg = thresholds.get("power") or {}
    w_warn = float(pcfg.get("watts_warn", 800))
    w_crit = float(pcfg.get("watts_crit", 1200))
    for pc in (snapshot.get("power") or {}).get("PowerControl") or []:
        w = pc.get("PowerConsumedWatts")
        if w is None:
            continue
        if w >= w_crit:
            findings.append(
                {"rule": "power", "severity": "crit", "message": f"整机功耗过高(>{w_crit}W): {w}W"}
            )
        elif w >= w_warn:
            findings.append(
                {"rule": "power", "severity": "warn", "message": f"功耗偏高(>{w_warn}W): {w}W"}
            )

    return findings
