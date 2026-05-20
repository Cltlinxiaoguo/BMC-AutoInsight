"""传感器展示逻辑测试。"""
from core.sensor_display import (
    NO_REPORT_MSG,
    OFF_SENSOR_MSG,
    apply_sensor_display,
    format_sensor_value,
    is_server_powered_off,
    none_sensor_message,
)


def test_format_none_off():
    assert format_sensor_value(None, "Off") == OFF_SENSOR_MSG
    assert format_sensor_value(42.5, "On") == 42.5


def test_format_none_on():
    assert format_sensor_value(None, "On") == NO_REPORT_MSG
    assert none_sensor_message("On") == NO_REPORT_MSG


def test_power_off_detect():
    assert is_server_powered_off("Off") is True
    assert is_server_powered_off("On") is False


def test_apply_sensor_display_off():
    inv = {
        "system": {"PowerState": "Off"},
        "thermal": {
            "Temperatures": [{"Name": "CPU", "ReadingCelsius": None}],
            "Fans": [{"Name": "FAN1", "Reading": None}],
        },
        "power": {"PowerControl": [{"PowerConsumedWatts": None}]},
    }
    out = apply_sensor_display(inv)
    assert out["thermal"]["Temperatures"][0]["ReadingCelsius"] == OFF_SENSOR_MSG
    assert out["thermal"]["Fans"][0]["Reading"] == OFF_SENSOR_MSG
    assert out["power"]["PowerControl"][0]["PowerConsumedWatts"] == OFF_SENSOR_MSG


def test_apply_sensor_display_on():
    inv = {
        "system": {"PowerState": "On"},
        "thermal": {
            "Temperatures": [{"Name": "M2_SSD1 Temp", "ReadingCelsius": None}],
            "Fans": [{"Name": "FAN3", "Reading": None}],
        },
        "power": {"PowerControl": [{"PowerConsumedWatts": 173}]},
    }
    out = apply_sensor_display(inv)
    assert out["thermal"]["Temperatures"][0]["ReadingCelsius"] == NO_REPORT_MSG
    assert out["thermal"]["Fans"][0]["Reading"] == NO_REPORT_MSG
    assert out["power"]["PowerControl"][0]["PowerConsumedWatts"] == 173
