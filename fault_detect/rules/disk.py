"""磁盘/存储规则：Storage 被跳过时不误报。"""


def check(data, thresholds):
    findings = []
    storage = data.get("storage") or {}
    if storage.get("_skipped") or storage.get("customer_notice_zh"):
        return findings
    members = storage.get("Members") or []
    if not members:
        findings.append({"rule": "disk", "severity": "warn", "message": "未发现存储成员"})
    return findings
