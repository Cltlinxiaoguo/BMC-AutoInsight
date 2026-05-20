"""URL / 凭证脱敏，用于日志输出。"""
from __future__ import annotations

import re
from urllib.parse import urlparse


def mask_url(url: str) -> str:
    """192.168.16.111 -> 192.168.*.* ; 保留 scheme 与 port。"""
    if not url:
        return "(未配置)"
    u = url.strip()
    if not u.startswith("http"):
        u = f"https://{u}"
    try:
        p = urlparse(u)
        host = p.hostname or ""
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            parts = host.split(".")
            masked = f"{parts[0]}.{parts[1]}.*.*"
        else:
            masked = host[:3] + "***" if len(host) > 3 else host
        port = f":{p.port}" if p.port else ""
        return f"{p.scheme}://{masked}{port}"
    except Exception:
        return "***"


def password_hint(password: str) -> str:
    """仅提示长度，不输出明文。"""
    if not password:
        return "(空密码)"
    if password in ("change_me", "password", "your_password"):
        return f"(占位符: {password})"
    return f"(已配置, 长度={len(password)})"
