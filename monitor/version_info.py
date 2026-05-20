def collect(client) -> dict:
    root = client.get_json("/redfish/v1/", optional=True)
    if root.get("_skipped"):
        return root
    return {
        "RedfishVersion": root.get("RedfishVersion"),
        "odata_id": root.get("@odata.id"),
        "Name": root.get("Name"),
    }
