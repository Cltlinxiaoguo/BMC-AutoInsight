"""API 冒烟：发现、合并、执行。"""
from pathlib import Path

import pytest

from api_test.discovery import extract_odata_ids, discover_get_paths, path_to_case_name
from api_test.runner import build_smoke_cases, merge_cases, run_auto_smoke
from core.mock_client import MockRedfishClient

FIXTURES = Path(__file__).parent / "fixtures" / "redfish_responses"
SMOKE_YAML = Path(__file__).resolve().parents[1] / "api_test" / "cases" / "smoke.yaml"


@pytest.fixture
def mock_client():
    return MockRedfishClient(FIXTURES)


def test_extract_odata_ids_from_actions():
    payload = {
        "@odata.id": "/redfish/v1/Systems/1",
        "Actions": {
            "#ComputerSystem.Reset": {
                "target": "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset"
            }
        },
        "Storage": {"@odata.id": "/redfish/v1/Systems/1/Storage"},
    }
    ids = extract_odata_ids(payload)
    assert "/redfish/v1/Systems/1" in ids
    assert "/redfish/v1/Systems/1/Storage" in ids
    assert "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset" in ids


def test_path_to_case_name():
    assert path_to_case_name("/redfish/v1/Systems/1/Thermal") == "systems_1_thermal"


def test_discover_get_paths_mock(mock_client):
    cases = discover_get_paths(mock_client, max_paths=20, max_depth=2)
    paths = {c["path"] for c in cases}
    assert "/redfish/v1/" in paths
    assert "/redfish/v1/Systems/1" in paths
    assert all(c["method"] == "GET" for c in cases)
    assert all(c["expect_status"] == 200 for c in cases)


def test_merge_cases_manual_over_auto():
    manual = [{"name": "root", "path": "/redfish/v1/", "method": "GET", "source": "manual"}]
    auto = [{"name": "auto_root", "path": "/redfish/v1/", "method": "GET", "source": "auto-discovered"}]
    merged = merge_cases(manual, auto)
    assert len(merged) == 1
    assert merged[0]["name"] == "root"


def test_run_auto_smoke_mock(mock_client):
    summary = run_auto_smoke(mock_client, SMOKE_YAML, max_paths=15)
    assert summary["total"] > 0
    assert summary["passed"] == summary["total"]
    assert summary["all_passed"] is True
    for row in summary["cases"]:
        assert row["passed"] is True
        assert row["status"] == 200
        assert "duration_ms" in row


def test_build_smoke_cases_includes_manual_and_auto(mock_client):
    cases = build_smoke_cases(mock_client, SMOKE_YAML, max_paths=15)
    names = {c["name"] for c in cases}
    assert "service_root" in names
    assert len(cases) >= 2
