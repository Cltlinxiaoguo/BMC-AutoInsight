"""超微等 BMC Redfish 电源控制：开机/关机/重启/状态查询。"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

from monitor.resolver import resolve_system_id

log = logging.getLogger("bmc_autoinsight")

# CLI 命令 -> Redfish ResetType
RESET_TYPES = {
    "power-on": "On",
    "power-off": "ForceOff",
    "power-restart": "ForceRestart",
    "on": "On",
    "off": "ForceOff",
    "restart": "ForceRestart",
    "reset": "ForceRestart",
    "force-restart": "ForceRestart",
    "graceful-shutdown": "GracefulShutdown",
    "graceful-restart": "GracefulRestart",
}

DANGEROUS_ACTIONS = frozenset({"power-off", "power-restart", "off", "restart", "reset", "force-restart", "graceful-shutdown"})

TARGET_STATE = {
    "On": {"On", "PoweringOn"},
    "ForceOff": {"Off", "PoweringOff"},
    "ForceRestart": {"On", "PoweringOn"},
    "GracefulShutdown": {"Off", "PoweringOff"},
    "GracefulRestart": {"On", "PoweringOn"},
}


def _system_paths(client: Any, cfg: Dict[str, Any]) -> Tuple[str, str, str]:
    bmc = cfg.get("bmc") or {}
    sys_id = resolve_system_id(client, bmc.get("system_id_override"))
    base = f"/redfish/v1/Systems/{sys_id}"
    action = f"{base}/Actions/ComputerSystem.Reset"
    return base, action, sys_id


def print_danger_banner(action: str) -> None:
    print("\n" + "!" * 56)
    print("  [危险操作警告]")
    if action in ("power-off", "off", "graceful-shutdown"):
        print("  即将对主机执行 **强制/远程关机**，业务将中断！")
        print("  请确认目标 IP 无误且已通知相关业务方。")
    elif action in ("power-restart", "restart", "reset", "force-restart", "graceful-restart"):
        print("  即将对主机执行 **远程重启**，所有未保存数据可能丢失！")
        print("  请确认目标 IP 无误且已通知相关业务方。")
    print("!" * 56 + "\n")


def get_power_status(client: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """实时读取 PowerState（只读，无需 confirm）。"""
    base, _, sys_id = _system_paths(client, cfg)
    try:
        data = client.get_json(base, optional=True)
    except Exception as exc:
        log.error("读取电源状态失败: %s", exc)
        return {"ok": False, "message": f"无法读取电源状态: {exc}"}

    if data.get("_skipped"):
        return {
            "ok": False,
            "message": f"读取失败 HTTP {data.get('_status')}",
            "system_id": sys_id,
        }

    state = data.get("PowerState")
    health = (data.get("Status") or {}).get("Health")
    log.info("PowerState=%s System=%s Health=%s", state, sys_id, health)
    return {
        "ok": True,
        "power_state": state,
        "health": health,
        "system_id": sys_id,
        "model": data.get("Model"),
        "manufacturer": data.get("Manufacturer"),
        "uri": base,
    }


def power_control(
    client: Any,
    cfg: Dict[str, Any],
    command: str,
    *,
    confirm: bool,
    execute: bool = False,
) -> Dict[str, Any]:
    """
    执行电源变更。必须 confirm=True。
    超微 BMC：POST .../Actions/ComputerSystem.Reset  Body: {"ResetType":"On|ForceOff|ForceRestart"}
    """
    cmd = command.lower().replace("_", "-")
    reset_type = RESET_TYPES.get(cmd)
    if not reset_type:
        return {"ok": False, "message": f"未知电源命令: {command}"}

    if not confirm:
        return {
            "ok": False,
            "message": (
                f"拒绝执行 {cmd}：必须添加 --confirm 参数。\n"
                f"示例: python main.py {cmd} --confirm"
            ),
        }

    if cmd in DANGEROUS_ACTIONS or reset_type in ("ForceOff", "ForceRestart", "GracefulShutdown"):
        print_danger_banner(cmd)

    pcfg = cfg.get("power") or {}
    dry = bool(pcfg.get("dry_run", True)) and not execute
    base, action_uri, sys_id = _system_paths(client, cfg)

    if dry:
        log.warning("[dry_run] 模拟电源操作 %s -> ResetType=%s (System %s)", cmd, reset_type, sys_id)
        return {
            "ok": True,
            "dry_run": True,
            "command": cmd,
            "reset_type": reset_type,
            "system_id": sys_id,
            "message": (
                f"[dry_run] 已模拟 {cmd}，未下发至 BMC。"
                " 加 --execute 可单次真实执行，或将 config 中 power.dry_run=false。"
            ),
        }

    payload = {"ResetType": reset_type}
    log.info("下发电源指令 POST %s ResetType=%s", action_uri, reset_type)
    try:
        r = client.request("POST", action_uri, json=payload)
    except Exception as exc:
        log.error("电源指令异常: %s", exc)
        return {"ok": False, "message": f"电源指令发送失败: {exc}"}

    if r.status_code not in (200, 202, 204):
        log.error("电源指令 HTTP %s: %s", r.status_code, getattr(r, "text", "")[:300])
        return {
            "ok": False,
            "status": r.status_code,
            "message": f"BMC 拒绝电源操作 HTTP {r.status_code}",
            "body": (getattr(r, "text", "") or "")[:500],
        }

    poll_interval = int((pcfg.get("poll") or {}).get("interval_sec", 5))
    poll_timeout = int((pcfg.get("poll") or {}).get("timeout_sec", 300))
    expected = TARGET_STATE.get(reset_type, set())

    deadline = time.time() + poll_timeout
    last_state = None
    log.info("开始轮询 PowerState，目标 %s，超时 %ss", expected or "任意", poll_timeout)
    while time.time() < deadline:
        st = get_power_status(client, cfg)
        if st.get("ok"):
            last_state = st.get("power_state")
            log.info("当前 PowerState=%s", last_state)
            if expected and last_state in expected:
                break
            if reset_type == "On" and last_state == "On":
                break
            if reset_type == "ForceOff" and last_state == "Off":
                break
        time.sleep(poll_interval)

    return {
        "ok": True,
        "command": cmd,
        "reset_type": reset_type,
        "status": r.status_code,
        "system_id": sys_id,
        "final_power_state": last_state,
        "message": f"{cmd} 指令已发送，当前 PowerState={last_state}",
    }


# 兼容旧 power 子命令
def power_action(client, action, config, *, confirm, double_ack=False):
    return power_control(client, config, action, confirm=confirm)
