"""从 Redfish JSON 响应中提取 @odata.id 与 Actions 链接。"""
from __future__ import annotations

import re
from typing import Any, Iterable, Set

# GET 冒烟不测试 POST Action 端点
_SKIP_PATH_PARTS = (
    "/Actions/",
    "/SessionService/Sessions",
    "/$metadata",
    "/odata/",
)


def path_to_case_name(path: str) -> str:
    """/redfish/v1/Systems/1/Thermal -> systems_1_thermal"""
    p = path.rstrip("/").split("/redfish/v1/")[-1]
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", p).strip("_").lower()
    return slug or "root"


def _should_skip_path(path: str) -> bool:
    if not path or not path.startswith("/"):
        return True
    return any(part in path for part in _SKIP_PATH_PARTS)


def extract_odata_ids(payload: Any, bucket: Set[str] | None = None) -> Set[str]:
    """递归收集 JSON 中所有 @odata.id。"""
    if bucket is None:
        bucket = set()
    if isinstance(payload, dict):
        oid = payload.get("@odata.id")
        if isinstance(oid, str) and oid.startswith("/"):
            bucket.add(oid)
        for key, val in payload.items():
            if key == "Actions" and isinstance(val, dict):
                for action in val.values():
                    if isinstance(action, dict):
                        target = action.get("target")
                        if isinstance(target, str):
                            bucket.add(target.split("?", 1)[0])
            extract_odata_ids(val, bucket)
    elif isinstance(payload, list):
        for item in payload:
            extract_odata_ids(item, bucket)
    return bucket


def filter_get_smoke_paths(paths: Iterable[str]) -> list[str]:
    """过滤出适合 GET 冒烟的路径（去重、排序）。"""
    out: list[str] = []
    seen: set[str] = set()
    for raw in sorted(set(paths)):
        path = raw.split("?", 1)[0]
        if path in seen or _should_skip_path(path):
            continue
        seen.add(path)
        out.append(path)
    return out


def discover_get_paths(
    client: Any,
    seeds: list[str] | None = None,
    *,
    max_paths: int = 50,
    max_depth: int = 3,
) -> list[dict[str, str]]:
    """
    从 ServiceRoot 起 BFS 爬取 @odata.id，生成 GET 冒烟候选。
    返回 [{"name","path","method","expect_status","source"}, ...]
    """
    seeds = seeds or ["/redfish/v1/"]
    queue: list[tuple[str, int]] = [(s, 0) for s in seeds]
    visited: set[str] = set()
    cases: list[dict[str, str]] = []

    while queue and len(cases) < max_paths:
        path, depth = queue.pop(0)
        norm = path.split("?", 1)[0]
        if norm in visited or _should_skip_path(norm):
            continue

        try:
            data = client.get_json(norm, optional=True)
        except Exception:
            visited.add(norm)
            continue

        status = data.get("_status")
        if data.get("_skipped") and status and int(status) != 200:
            visited.add(norm)
            continue
        if not isinstance(data, dict):
            visited.add(norm)
            continue

        visited.add(norm)
        cases.append(
            {
                "name": path_to_case_name(norm),
                "path": norm,
                "method": "GET",
                "expect_status": 200,
                "source": "auto-discovered",
            }
        )

        if depth >= max_depth:
            continue
        if data.get("_skipped"):
            continue

        for link in extract_odata_ids(data):
            link_norm = link.split("?", 1)[0]
            if link_norm not in visited and not _should_skip_path(link_norm):
                queue.append((link_norm, depth + 1))

    return cases
