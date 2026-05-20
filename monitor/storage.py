"""存储采集；超微等厂商可能对 Storage 集合返回 403，需对客户明确说明。"""


def collect(client, system_id: str = "1") -> dict:
    path = f"/redfish/v1/Systems/{system_id}/Storage"
    r = client.get_json(path, optional=True)
    if r.get("_status") == 403:
        r["customer_notice_zh"] = (
            "【存储模块权限受限，厂商未开放，已跳过检测】当前账号或固件策略禁止访问 "
            f"`{path}`。磁盘/RAID 健康请在厂商 Web 或开放 Redfish 权限后重试。"
        )
    elif r.get("_status") == 404:
        r["customer_notice_zh"] = (
            "【存储模块】Redfish 未返回 Storage 集合(404)，可能为该机未启用此 URI，已跳过。"
        )
    return r
