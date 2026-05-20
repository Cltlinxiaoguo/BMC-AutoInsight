def collect(client, chassis_id: str = "1") -> dict:
    return client.get_json(f"/redfish/v1/Chassis/{chassis_id}/Power", optional=True)
