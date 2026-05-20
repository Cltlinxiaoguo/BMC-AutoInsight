def check(data, thresholds):
    findings = []
    thermal = data.get("thermal") or {}
    f_cfg = thresholds.get("fan") or {}
    warn_min = float(f_cfg.get("min_rpm_warn", 1500))
    crit_min = float(f_cfg.get("min_rpm_crit", 800))
    for fan in thermal.get("Fans") or []:
        rpm = fan.get("Reading") or fan.get("ReadingRPM")
        if rpm is None:
            continue
        name = fan.get("Name") or fan.get("MemberId") or "fan"
        if rpm < crit_min:
            findings.append(
                {
                    "rule": "fan",
                    "severity": "crit",
                    "message": f"{name} 转速低于严重下限({crit_min} RPM): {rpm} RPM",
                }
            )
        elif rpm < warn_min:
            findings.append(
                {
                    "rule": "fan",
                    "severity": "warn",
                    "message": f"{name} 转速偏低(<{warn_min} RPM): {rpm} RPM",
                }
            )
    return findings
