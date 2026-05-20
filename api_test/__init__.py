"""Redfish API 冒烟测试：自动发现、执行与报告。"""

from api_test.discovery import discover_get_paths, extract_odata_ids
from api_test.runner import run_auto_smoke, print_smoke_results

__all__ = [
    "discover_get_paths",
    "extract_odata_ids",
    "run_auto_smoke",
    "print_smoke_results",
]
