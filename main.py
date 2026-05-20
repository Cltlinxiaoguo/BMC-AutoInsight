#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BMC AutoInsight — 企业版 CLI（Redfish 巡检 / 告警 / 批量 / 电源）。"""
from __future__ import annotations

from datetime import datetime
import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_loader import load_app_config, load_thresholds
from core.logger import setup_logging
from core.auth import SessionManager, print_login_failure
from core.client import RedfishClient
from core.mock_client import MockRedfishClient
from monitor.collector import collect_all
from monitor.hardware_info import collect_hardware_info, print_hardware_info
from fault_detect.engine import run_fault_checks
from api_test.runner import run_auto_smoke, print_smoke_results
from api_test.report_export import export_api_smoke_bundle
from control.power import power_control, get_power_status
from core.sensor_display import apply_sensor_display, print_sensor_summary
from core.report_cleaner import clean_reports, print_clean_reports_summary
from reports.exporter import export_inspection_bundle


def _merge_bmc(cfg: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    b = dict(cfg.get("bmc") or {})
    if not override:
        return b
    port_override = override.get("port")
    host_override = override.get("host")
    for k, v in override.items():
        if k in ("port",):
            continue
        if v is None or str(v).strip() == "":
            continue
        b[k] = v
    if host_override:
        h = str(host_override).strip()
        if h.startswith("http"):
            b["host"] = h
        elif port_override:
            p = int(port_override)
            b["host"] = f"https://{h}" if p in (443, 80) else f"https://{h}:{p}"
        else:
            b["host"] = f"https://{h}"
    return b


def _build_session_manager(cfg: Dict[str, Any], bmc_override: Optional[Dict[str, Any]] = None) -> SessionManager:
    bmc = _merge_bmc(cfg, bmc_override)
    base = bmc.get("host") or "https://127.0.0.1"
    if not str(base).startswith("http"):
        base = f"https://{base}"
    retry = cfg.get("retry") or {}
    basic = cfg.get("basic") or {}
    return SessionManager(
        base,
        str(bmc.get("username", "admin")),
        str(bmc.get("password", "")),
        verify_ssl=bool(bmc.get("verify_ssl", False)),
        read_timeout=int(bmc.get("read_timeout") or 120),
        connect_timeout=int(bmc.get("connect_timeout") or 10),
        keepalive_sec=int(bmc.get("session_keepalive_sec") or 0),
        preferred_mode=str(bmc.get("auth_mode") or basic.get("auth_mode") or "auto"),
        login_max_attempts=int(retry.get("login_attempts") or basic.get("login_attempts") or 3),
        login_backoff_sec=float(retry.get("backoff_base_sec") or 2),
    )


def _client(args: Any, cfg: Dict[str, Any], bmc_override: Optional[Dict[str, Any]] = None) -> Any:
    if args.mock:
        fix = ROOT / "tests" / "fixtures" / "redfish_responses"
        return MockRedfishClient(fix)

    sm = _build_session_manager(cfg, bmc_override)
    result = sm.login_with_retry(config_source=str(cfg.get("config_source", "")))
    if not result.ok:
        print_login_failure(result)
        return None

    retry_cfg = cfg.get("retry") or {}
    return RedfishClient(
        sm,
        max_retries=int(retry_cfg.get("max_attempts") or 4),
        retry_cfg=retry_cfg,
    )


def _apply_logging(cfg: Dict[str, Any]) -> None:
    lg = cfg.get("logging") or {}
    setup_logging(str(lg.get("level", "INFO")), str(lg.get("dir", "logs")))


def _run_api_smoke(client: Any, max_paths: int = 50) -> Dict[str, Any]:
    case_path = ROOT / "api_test" / "cases" / "smoke.yaml"
    return run_auto_smoke(client, case_path, max_paths=max_paths)


def _collect_hardware(client: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
    bmc = cfg.get("bmc") or {}
    return collect_hardware_info(
        client,
        system_id_override=bmc.get("system_id_override"),
        chassis_id_override=bmc.get("chassis_id_override"),
        manager_id_override=bmc.get("manager_id_override"),
    )


def cmd_inspect(args: argparse.Namespace) -> int:
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    client = _client(args, cfg)
    if client is None:
        return 1
    bmc = cfg.get("bmc") or {}
    timeout = int(bmc.get("inspection_timeout") or 0)
    result = collect_all(
        client,
        host=str(bmc.get("host", "bmc")),
        mock=args.mock,
        inspection_timeout_sec=timeout,
        system_id_override=bmc.get("system_id_override"),
        chassis_id_override=bmc.get("chassis_id_override"),
    )
    th = load_thresholds(ROOT)
    snap = {
        "thermal": result.thermal,
        "power": result.power,
        "storage": result.storage,
        "system": result.system,
    }
    faults = run_fault_checks(snap, th)
    result.faults = faults
    inv_dict = apply_sensor_display(result.to_dict())
    print_sensor_summary(inv_dict)
    hardware = _collect_hardware(client, cfg)
    print_hardware_info(hardware)
    api_summary = _run_api_smoke(client, max_paths=50)
    print_smoke_results(api_summary)
    payload = {
        "timestamp": result.timestamp,
        "host": result.host,
        "mock": result.mock,
        "inspection": inv_dict,
        "faults": faults,
        "hardware_info": hardware,
        "api_test": api_summary.get("cases") or [],
    }
    report_root = ROOT / "reports"
    paths = export_inspection_bundle(report_root, payload, exports=getattr(args, "exports", "json,html,txt,xlsx"))
    print("巡检完成", result.system.get("Model"), result.system.get("SerialNumber"))
    for k, v in paths.items():
        print(f"  [{k}] {v}")
    return 0


def cmd_fault_check(args: argparse.Namespace) -> int:
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    client = _client(args, cfg)
    if client is None:
        return 1
    bmc = cfg.get("bmc") or {}
    result = collect_all(
        client,
        host=str(bmc.get("host", "bmc")),
        mock=args.mock,
        inspection_timeout_sec=int(bmc.get("inspection_timeout") or 0),
        system_id_override=bmc.get("system_id_override"),
        chassis_id_override=bmc.get("chassis_id_override"),
    )
    th = load_thresholds(ROOT)
    snap = {
        "thermal": result.thermal,
        "power": result.power,
        "storage": result.storage,
        "system": result.system,
    }
    faults = run_fault_checks(snap, th)
    result.faults = faults
    inv_dict = apply_sensor_display(result.to_dict())
    print_sensor_summary(inv_dict)
    hardware = _collect_hardware(client, cfg)
    print_hardware_info(hardware)
    api_summary = _run_api_smoke(client, max_paths=50)
    print_smoke_results(api_summary)
    payload = {
        "timestamp": result.timestamp,
        "host": result.host,
        "mock": result.mock,
        "inspection": inv_dict,
        "faults": faults,
        "hardware_info": hardware,
        "api_test": api_summary.get("cases") or [],
    }
    paths = export_inspection_bundle(ROOT / "reports", payload, exports=getattr(args, "exports", "json,html,txt,xlsx"))
    for f in faults:
        print(f"[{f.get('severity')}] {f.get('rule')}: {f.get('message')}")
    print(f"共 {len(faults)} 条告警 / 提示")
    for k, v in paths.items():
        print(f"  [{k}] {v}")
    return 0


def cmd_hardware_info(args: argparse.Namespace) -> int:
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    client = _client(args, cfg)
    if client is None:
        return 1
    bmc = cfg.get("bmc") or {}
    hardware = _collect_hardware(client, cfg)
    print_hardware_info(hardware)
    api_summary = _run_api_smoke(client, max_paths=int(getattr(args, "max_paths", 50) or 50))
    print_smoke_results(api_summary)
    payload = {
        "timestamp": datetime.now().isoformat(),
        "host": str(bmc.get("host", "")),
        "mock": args.mock,
        "hardware_info": hardware,
        "api_test": api_summary.get("cases") or [],
    }
    paths = export_inspection_bundle(
        ROOT / "reports",
        payload,
        exports=getattr(args, "exports", "json,html,txt,xlsx"),
        prefix="hardware",
    )
    for k, v in paths.items():
        print(f"  [{k}] {v}")
    return 0 if api_summary.get("all_passed") else 1


def cmd_api_test(args: argparse.Namespace) -> int:
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    client = _client(args, cfg)
    if client is None:
        return 1
    case_path = ROOT / "api_test" / "cases" / "smoke.yaml"
    max_paths = int(getattr(args, "max_paths", 50) or 50)
    summary = run_auto_smoke(client, case_path, max_paths=max_paths)
    print_smoke_results(summary)
    bmc = cfg.get("bmc") or {}
    paths = export_api_smoke_bundle(
        ROOT / "reports",
        summary,
        host=str(bmc.get("host", "")),
    )
    # 同步写入带 API 表格的 HTML/Excel 汇总（避免报告空白）
    bundle_paths = export_inspection_bundle(
        ROOT / "reports",
        {"host": bmc.get("host"), "api_test": summary.get("cases") or [], "hardware_info": {}},
        exports="html,xlsx",
        prefix="api_smoke",
    )
    paths.update({k: v for k, v in bundle_paths.items() if v})
    for k, v in paths.items():
        print(f"  [{k}] {v}")
    return 0 if summary.get("all_passed") else 1


def cmd_clean_reports(args: argparse.Namespace) -> int:
    """清理 reports 目录下的历史导出（不连接 BMC）。"""
    if int(args.keep) < 1:
        print("[ERROR] --keep 须为 >= 1 的整数")
        return 2
    res = clean_reports(
        ROOT / "reports",
        keep=int(args.keep),
        dry_run=bool(args.dry_run),
    )
    print_clean_reports_summary(res, dry_run=bool(args.dry_run))
    return 0


def _run_power_cmd(args: argparse.Namespace, command: str) -> int:
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    client = _client(args, cfg)
    if client is None:
        return 1
    out = power_control(
        client,
        cfg,
        command,
        confirm=bool(args.confirm),
        execute=bool(getattr(args, "execute", False)),
    )
    print("\n" + "=" * 50)
    if out.get("ok"):
        print(f"[成功] {out.get('message', command)}")
        if out.get("final_power_state"):
            print(f"  PowerState: {out.get('final_power_state')}")
        if out.get("dry_run"):
            print("  (dry_run 模式，未真实下发)")
    else:
        print(f"[失败] {out.get('message')}")
    print("=" * 50 + "\n")
    return 0 if out.get("ok") else 1


def cmd_power_on(args: argparse.Namespace) -> int:
    return _run_power_cmd(args, "power-on")


def cmd_power_off(args: argparse.Namespace) -> int:
    return _run_power_cmd(args, "power-off")


def cmd_power_restart(args: argparse.Namespace) -> int:
    return _run_power_cmd(args, "power-restart")


def cmd_power_status(args: argparse.Namespace) -> int:
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    client = _client(args, cfg)
    if client is None:
        return 1
    out = get_power_status(client, cfg)
    print("\n" + "=" * 50)
    print("BMC 电源状态")
    print("=" * 50)
    if out.get("ok"):
        print(f"  System ID   : {out.get('system_id')}")
        print(f"  PowerState  : {out.get('power_state')}")
        print(f"  Health      : {out.get('health')}")
        print(f"  Model       : {out.get('model')}")
        print(f"  Manufacturer: {out.get('manufacturer')}")
        print(f"  URI         : {out.get('uri')}")
    else:
        print(f"  [失败] {out.get('message')}")
    print("=" * 50 + "\n")
    return 0 if out.get("ok") else 1


def cmd_power(args: argparse.Namespace) -> int:
    """兼容旧版 power 子命令。"""
    action = getattr(args, "action", "reset") or "reset"
    mapping = {"on": "power-on", "off": "power-off", "reset": "power-restart"}
    cmd = mapping.get(action.lower(), action)
    return _run_power_cmd(args, cmd)


def cmd_login_test(args: argparse.Namespace) -> int:
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    if args.mock:
        print("[Mock] 跳过真实 BMC 登录")
        return 0

    sm = _build_session_manager(cfg)
    result = sm.login_with_retry(config_source=str(cfg.get("config_source", "")))
    if result.ok:
        print("\n" + "=" * 50)
        print("BMC 登录成功")
        print("=" * 50)
        print(f"  认证方式 : {result.auth_mode}")
        print(f"  Session  : {result.session_id or 'N/A (Basic 模式)'}")
        print(f"  HTTP状态 : {result.status_code}")
        print(f"  尝试次数 : {result.attempts}")
        print("=" * 50 + "\n")
        return 0

    print_login_failure(result)
    return 1


def cmd_demo(args: argparse.Namespace) -> int:
    args.mock = True
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    th = load_thresholds(ROOT)
    client = _client(args, cfg)
    result = collect_all(client, host="demo-mock", mock=True, inspection_timeout_sec=0)
    snap = {
        "thermal": result.thermal,
        "power": result.power,
        "storage": result.storage,
        "system": result.system,
    }
    result.faults = run_fault_checks(snap, th)
    hardware = _collect_hardware(client, cfg)
    print_hardware_info(hardware)
    api_summary = _run_api_smoke(client, max_paths=30)
    result.api_results = api_summary.get("cases") or []
    print_smoke_results(api_summary)
    payload = {
        "timestamp": result.timestamp,
        "host": result.host,
        "mock": True,
        "inspection": apply_sensor_display(result.to_dict()),
        "faults": result.faults,
        "hardware_info": hardware,
        "api_test": result.api_results,
    }
    paths = export_inspection_bundle(ROOT / "reports", payload, exports="json,html,txt,xlsx")
    print("Demo 完成 (Mock)")
    for k, v in paths.items():
        print(f"  [{k}] {v}")
    print("故障数:", len(result.faults))
    return 0


def cmd_batch_inspect(args: argparse.Namespace) -> int:
    cfg = load_app_config(ROOT)
    _apply_logging(cfg)
    p = Path(args.file)
    if not p.exists():
        print("找不到批量文件:", p)
        return 2
    rows: list[dict[str, str]] = []
    with p.open("r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row:
                continue
            h = (row.get("host") or "").strip()
            if not h or h.startswith("#"):
                continue
            rows.append({k.strip(): (v or "").strip() for k, v in row.items() if k})

    if not rows:
        print("批量文件无有效行")
        return 1

    all_payload: list[Dict[str, Any]] = []
    rc = 0
    for row in rows:
        ov: Dict[str, Any] = {
            "username": row.get("username"),
            "password": row.get("password"),
        }
        vs = row.get("verify_ssl")
        if vs is not None and str(vs).strip() != "":
            ov["verify_ssl"] = str(vs).lower() in ("true", "1", "yes")
        host = row.get("host", "")
        if "port" in row and row["port"]:
            ov["port"] = int(row["port"])
            ov["host"] = host
        else:
            ov["host"] = host

        try:
            client = _client(args, cfg, bmc_override=ov)
            if client is None:
                rc = 1
                all_payload.append({"host": host, "error": "login failed", "faults": []})
                continue
            bmc_merge = _merge_bmc(cfg, ov)
            it_out = (cfg.get("basic") or {}).get("inspection_timeout")
            it = int(bmc_merge.get("inspection_timeout") or it_out or 0)
            result = collect_all(
                client,
                host=str(bmc_merge.get("host")),
                mock=False,
                inspection_timeout_sec=it,
                system_id_override=bmc_merge.get("system_id_override"),
                chassis_id_override=bmc_merge.get("chassis_id_override"),
            )
            th = load_thresholds(ROOT)
            snap = {
                "thermal": result.thermal,
                "power": result.power,
                "storage": result.storage,
                "system": result.system,
            }
            faults = run_fault_checks(snap, th)
            result.faults = faults
            inv_dict = apply_sensor_display(result.to_dict())
            hardware = collect_hardware_info(
                client,
                system_id_override=bmc_merge.get("system_id_override"),
                chassis_id_override=bmc_merge.get("chassis_id_override"),
                manager_id_override=bmc_merge.get("manager_id_override"),
            )
            api_summary = _run_api_smoke(client, max_paths=30)
            all_payload.append(
                {
                    "host": result.host,
                    "timestamp": result.timestamp,
                    "faults": faults,
                    "inspection": inv_dict,
                    "hardware_info": hardware,
                    "api_test": api_summary.get("cases") or [],
                }
            )
        except Exception as exc:
            rc = 1
            all_payload.append({"host": host, "error": str(exc), "faults": []})
            print(f"[ERROR] {host} -> {exc}")

    bundle = {"batch": True, "count": len(rows), "results": all_payload}
    paths = export_inspection_bundle(ROOT / "reports", bundle, exports=getattr(args, "exports", "json,html,txt,xlsx"))
    print("批量巡检结束，汇总条目:", len(all_payload))
    for k, v in paths.items():
        print(f"  [{k}] {v}")
    return rc


POWER_HELP_EPILOG = """
电源控制命令（变更操作必须加 --confirm，否则拒绝执行）:
  power-on        远程开机 (ResetType=On)
  power-off       远程强制关机 [危险] (ResetType=ForceOff)
  power-restart   远程重启 [危险] (ResetType=ForceRestart)
  power-status    查看当前 PowerState（只读，无需 --confirm）

示例:
  python main.py power-status
  python main.py power-on --confirm --execute

说明: 默认 dry_run 仅模拟；真实操作须加 --execute，或 config 中 power.dry_run=false
"""


def _add_power_confirm(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--confirm",
        action="store_true",
        help="确认执行电源变更（必填，否则拒绝）",
    )
    sp.add_argument(
        "--execute",
        action="store_true",
        help="忽略 dry_run，向 BMC 真实下发电源指令（须与 --confirm 同用）",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bmc-autoinsight",
        description="BMC AutoInsight 企业版 — Redfish 巡检 / 告警 / 电源控制",
        epilog=POWER_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--mock", action="store_true", help="使用本地 Mock 夹具，不连接 BMC")

    sub = p.add_subparsers(dest="command", required=True)

    def add_export(s: argparse.ArgumentParser) -> None:
        s.add_argument(
            "--exports",
            default="json,html,txt,xlsx",
            help="导出格式，逗号分隔：json,html,txt,xlsx",
        )

    sp = sub.add_parser("inspect", help="单目标 Redfish 巡检")
    add_export(sp)
    sp.set_defaults(func=cmd_inspect)

    fc = sub.add_parser("fault-check", help="巡检并执行规则告警")
    add_export(fc)
    fc.set_defaults(func=cmd_fault_check)

    hi = sub.add_parser("hardware-info", help="硬件信息与固件版本查询")
    add_export(hi)
    hi.add_argument("--max-paths", type=int, default=50, help="附带 API 冒烟最大路径数")
    hi.set_defaults(func=cmd_hardware_info)

    at = sub.add_parser("api-test", help="Redfish API 自动发现冒烟测试")
    at.add_argument("--max-paths", type=int, default=50, help="自动发现最大 GET 路径数")
    at.set_defaults(func=cmd_api_test)

    cr = sub.add_parser(
        "clean-reports",
        help="清理 reports/ 历史导出（按导出时间戳归组保留最近若干组，.py 源码不删除）",
    )
    cr.add_argument(
        "--keep",
        type=int,
        default=5,
        metavar="N",
        help="保留最近 N 组时间戳导出（每组可含 html/json/xlsx/txt 等多格式，默认 5）",
    )
    cr.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览将删除/保留的文件，不实际删除",
    )
    cr.set_defaults(func=cmd_clean_reports)

    po = sub.add_parser("power-on", help="远程开机 (需 --confirm)")
    _add_power_confirm(po)
    po.set_defaults(func=cmd_power_on)

    pf = sub.add_parser("power-off", help="远程强制关机 [危险] (需 --confirm)")
    _add_power_confirm(pf)
    pf.set_defaults(func=cmd_power_off)

    pr = sub.add_parser("power-restart", help="远程重启 [危险] (需 --confirm)")
    _add_power_confirm(pr)
    pr.set_defaults(func=cmd_power_restart)

    sub.add_parser("power-status", help="查看 PowerState（只读）").set_defaults(func=cmd_power_status)

    pw = sub.add_parser("power", help="[兼容] 旧版电源命令 on|off|reset")
    pw.add_argument("action", nargs="?", default="reset", help="on | off | reset")
    _add_power_confirm(pw)
    pw.set_defaults(func=cmd_power)

    sub.add_parser("login-test", help="会话登录").set_defaults(func=cmd_login_test)
    sub.add_parser("demo", help="Mock 全流程 + 报告").set_defaults(func=cmd_demo)

    bi = sub.add_parser("batch-inspect", help="CSV 批量 BMC 巡检")
    bi.add_argument("--file", "-f", required=True, help="CSV 路径（参见 config/batch_targets.example.csv）")
    add_export(bi)
    bi.set_defaults(func=cmd_batch_inspect)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
