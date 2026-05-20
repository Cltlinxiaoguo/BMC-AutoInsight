"""认证相关测试."""
from core.auth import SessionManager, PLACEHOLDER_PASSWORDS


def test_session_manager_attrs():
    sm = SessionManager("https://bmc.local", "u", "p")
    assert sm.username == "u"
    assert sm.preferred_mode == "auto"


def test_placeholder_passwords():
    assert "change_me" in PLACEHOLDER_PASSWORDS
