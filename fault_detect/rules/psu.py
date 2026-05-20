def check(data, thresholds):
    findings = []
    power = data.get("power") or {}
    min_v = (thresholds.get("psu") or {}).get("min_input_voltage", 200)
    for psu in power.get("PowerSupplies") or []:
        v = psu.get("LineInputVoltage")
        if v is not None and v < min_v:
            findings.append({
                "rule": "psu",
                "severity": "crit",
                "message": f"{psu.get('MemberId')} 输入电压过低: {v}V",
            })
    return findings
