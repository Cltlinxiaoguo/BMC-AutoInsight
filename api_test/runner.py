"""Redfish API 冒烟：自动发现路径、执行 GET、输出结果。"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List

import yaml

from api_test.discovery import discover_get_paths, path_to_case_name

log = logging.getLogger("bmc_autoinsight")


def load_cases(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("cases") or [])


def merge_cases(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 path 去重，manual 优先于 auto。"""
    merged: dict[str, Dict[str, Any]] = {}
    for group in groups:
        for c in group:
            path = (c.get("path") or "").split("?", 1)[0]
            if not path:
                continue
            key = f"{(c.get('method') or 'GET').upper()}:{path}"
            if key not in merged or c.get("source") != "auto-discovered":
                merged[key] = dict(c)
    return list(merged.values())


def build_smoke_cases(client: Any, yaml_path: Path | None = None, *, max_paths: int = 50) -> List[Dict[str, Any]]:
    manual = load_cases(yaml_path) if yaml_path else []
    auto = discover_get_paths(client, max_paths=max_paths)
    return merge_cases(manual, auto)


def run_cases(client: Any, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """执行用例，返回含 duration_ms / passed / error 的结果列表。"""
    results: List[Dict[str, Any]] = []
    for c in cases:
        method = (c.get("method") or "GET").upper()
        path = c.get("path") or "/redfish/v1/"
        expect = int(c.get("expect_status", 200))
        name = c.get("name") or path_to_case_name(path)
        t0 = time.perf_counter()
        status: int | None = None
        error: str | None = None
        try:
            if method == "GET":
                if hasattr(client, "request"):
                    r = client.request("GET", path, auth_refresh=False)
                    status = r.status_code
                else:
                    client.get_json(path)
                    status = 200
            else:
                error = f"冒烟暂不支持 {method}"
        except Exception as exc:
            error = str(exc)
            log.warning("冒烟用例异常 %s %s: %s", name, path, exc)
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        passed = status == expect and error is None
        row = {
            "name": name,
            "path": path,
            "method": method,
            "status": status,
            "expect": expect,
            "passed": passed,
            "duration_ms": duration_ms,
            "source": c.get("source", "manual"),
            "error": error,
        }
        results.append(row)
        log.info(
            "API冒烟 [%s] %s %s -> %s (%sms) %s",
            "PASS" if passed else "FAIL",
            method,
            path,
            status,
            duration_ms,
            name,
        )
    return results


def run_auto_smoke(
    client: Any,
    yaml_path: Path | None = None,
    *,
    max_paths: int = 50,
) -> Dict[str, Any]:
    """自动发现 + 执行，返回汇总结构。"""
    cases = build_smoke_cases(client, yaml_path, max_paths=max_paths)
    results = run_cases(client, cases)
    passed = sum(1 for r in results if r.get("passed"))
    failed = len(results) - passed
    return {
        "cases": results,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "all_passed": failed == 0 and len(results) > 0,
    }


def print_smoke_results(summary: Dict[str, Any]) -> None:
    """控制台表格输出。"""
    rows = summary.get("cases") or []
    print("\n" + "=" * 72)
    print("API 冒烟测试结果")
    print("=" * 72)
    print(f"{'用例名称':<28} {'HTTP':<6} {'结果':<6} {'耗时ms':<8} 接口路径")
    print("-" * 72)
    for r in rows:
        name = str(r.get("name", ""))[:26]
        status = r.get("status")
        st = str(status) if status is not None else "ERR"
        ok = "PASS" if r.get("passed") else "FAIL"
        ms = r.get("duration_ms", "")
        path = r.get("path", "")
        print(f"{name:<28} {st:<6} {ok:<6} {ms:<8} {path}")
    print("-" * 72)
    print(
        f"总计: {summary.get('total', 0)}  "
        f"通过: {summary.get('passed', 0)}  "
        f"失败: {summary.get('failed', 0)}"
    )
    print("=" * 72 + "\n")
