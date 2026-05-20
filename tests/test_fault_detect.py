"""故障检测 mock 数据测试."""
from pathlib import Path
import json
from fault_detect.engine import run_fault_checks
from core.config_loader import load_thresholds

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "redfish_responses"

def test_fault_detect_with_fixtures():
    thermal = json.loads((FIX / "thermal.json").read_text(encoding="utf-8"))
    power = json.loads((FIX / "power.json").read_text(encoding="utf-8"))
    storage = json.loads((FIX / "storage.json").read_text(encoding="utf-8"))
    th = load_thresholds(ROOT)
    findings = run_fault_checks({"thermal": thermal, "power": power, "storage": storage}, th)
    assert isinstance(findings, list)
