"""清理 reports/ 历史导出：按同一时间戳前缀归组，保留最新若干组。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# 与 exporter 导出前缀一致：<name>_YYYYMMDD_HHMMSS.ext
_TS_STEM = re.compile(r"^.+_\d{8}_\d{6}$")

# 永不清除：源码与其它非导出文件
_PROTECTED_SUFFIXES = frozenset({".py"})


@dataclass
class CleanReportsResult:
    """清理结果摘要。"""

    kept_paths: list[Path] = field(default_factory=list)
    deleted_paths: list[Path] = field(default_factory=list)
    skipped_protected: list[Path] = field(default_factory=list)
    skipped_no_ts: list[Path] = field(default_factory=list)


def _is_protected(path: Path) -> bool:
    return not path.is_file() or path.suffix.lower() in _PROTECTED_SUFFIXES


def _group_key(path: Path) -> str | None:
    """若文件名符合导出时间戳模式，返回分组键（无扩展名的 stem）；否则不参与清理。"""
    stem = path.stem
    if _TS_STEM.match(stem):
        return stem
    return None


def clean_reports(
    report_dir: Path,
    *,
    keep: int = 5,
    dry_run: bool = False,
) -> CleanReportsResult:
    """
    扫描 report_dir 下**一层**的普通文件：
    - 将 stem 形如 ``xxx_YYYYMMDD_HHMMSS`` 的文件归为一组（同一次导出多格式）；
    - 按组内最新修改时间排序，保留最近 ``keep`` 组，其余组整组删除；
    - ``.py`` 等受保护后缀永不删除；
    - 不匹配时间戳 stem 的文件：保留且不删除。
    """
    keep = max(1, int(keep))
    result = CleanReportsResult()

    if not report_dir.is_dir():
        return result

    grouped: dict[str, list[Path]] = {}
    for path in sorted(report_dir.iterdir()):
        if not path.is_file():
            continue
        if _is_protected(path):
            result.skipped_protected.append(path)
            continue
        key = _group_key(path)
        if key is None:
            result.skipped_no_ts.append(path)
            continue
        grouped.setdefault(key, []).append(path)

    if not grouped:
        return result

    def newest_mtime(paths: list[Path]) -> float:
        return max(p.stat().st_mtime for p in paths)

    # 按组最新修改时间降序
    ordered = sorted(grouped.items(), key=lambda kv: newest_mtime(kv[1]), reverse=True)

    keep_keys = {k for k, _ in ordered[:keep]}
    for key, paths in grouped.items():
        paths_sorted = sorted(paths, key=lambda p: p.name)
        if key in keep_keys:
            result.kept_paths.extend(paths_sorted)
        else:
            for p in paths_sorted:
                if dry_run:
                    result.deleted_paths.append(p)
                else:
                    p.unlink(missing_ok=True)
                    result.deleted_paths.append(p)

    result.kept_paths.sort(key=lambda p: p.name)
    result.deleted_paths.sort(key=lambda p: p.name)
    result.skipped_protected.sort(key=lambda p: p.name)
    result.skipped_no_ts.sort(key=lambda p: p.name)
    return result


def print_clean_reports_summary(res: CleanReportsResult, *, dry_run: bool) -> None:
    """控制台输出保留 / 删除 / 跳过。"""
    mode = "预览（dry-run，未删除）" if dry_run else "已完成删除"
    print("\n" + "=" * 64)
    print(f"reports 目录清理 — {mode}")
    print("=" * 64)

    if res.skipped_protected:
        print("\n【跳过 — 受保护文件】（未参与清理统计）")
        for p in res.skipped_protected:
            print(f"  KEEP (protected) {p}")

    if res.skipped_no_ts:
        print("\n【跳过 — 非标准时间戳命名】（视为非自动导出或未识别，已全部保留）")
        for p in res.skipped_no_ts:
            print(f"  KEEP (no-ts-stem) {p}")

    print("\n【保留】导出组内文件（按本次策略应保留的报告）")
    if not res.kept_paths:
        print("  (无匹配的按时间戳分组的导出文件)")
    else:
        for p in res.kept_paths:
            print(f"  KEEP {p}")

    print("\n【删除】" + ("以下内容仅预览，磁盘未改动" if dry_run else ""))
    if not res.deleted_paths:
        print("  (无)")
    else:
        tag = "[将删除]" if dry_run else "[已删除]"
        for p in res.deleted_paths:
            print(f"  {tag} {p}")

    print("=" * 64 + "\n")
