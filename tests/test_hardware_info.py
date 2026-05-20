"""硬件信息采集测试。"""
from pathlib import Path

from core.mock_client import MockRedfishClient
from monitor.hardware_info import collect_hardware_info, print_hardware_info

FIXTURES = Path(__file__).parent / "fixtures" / "redfish_responses"


def test_collect_hardware_info_mock(capsys):
    client = MockRedfishClient(FIXTURES)
    info = collect_hardware_info(client)
    s = info["summary"]
    assert s["model"] == "DemoServer"
    assert s["serial_number"] == "SN-DEMO-001"
    assert s["bios_version"] == "3.4a"
    assert s["bmc_firmware_version"] == "01.02.03"
    assert len(info["cpu"]) >= 1
    assert info["memory"]["total_gib"] == 128
    assert len(info["memory"]["modules"]) == 1
    assert len(info["disks"]) == 1
    assert info["motherboard"]["part_number"] == "MB-DEMO-01"
    print_hardware_info(info)
    out = capsys.readouterr().out
    assert "硬件信息与固件版本" in out
    assert "BIOS 版本" in out
