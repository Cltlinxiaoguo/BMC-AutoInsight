"""Redfish 认证：Session Token / Basic Auth 自动回退、重试、友好错误。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

from core.util_mask import mask_url, password_hint

log = logging.getLogger("bmc_autoinsight")

# 占位密码：若 ini 示例未改且 yaml 有真实密码则自动合并
PLACEHOLDER_PASSWORDS = frozenset(
    {"", "change_me", "password", "your_password", "changeme"}
)


@dataclass
class LoginResult:
    ok: bool
    auth_mode: str = ""  # session | basic
    session_id: Optional[str] = None
    token: Optional[str] = None
    message: str = ""
    status_code: Optional[int] = None
    attempts: int = 0
    detail: str = ""


class SessionManager:
    """
    Redfish 认证管理器。
    - auto：先 Session (POST Sessions)，401 时回退 Basic Auth 验证
    - session：仅 Session
    - basic：仅 HTTP Basic（超微等部分场景 Session 受限时可用）
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
        timeout: int = 120,
        connect_timeout: int = 10,
        read_timeout: int = 120,
        keepalive_sec: int = 0,
        preferred_mode: str = "auto",
        login_max_attempts: int = 3,
        login_backoff_sec: float = 2.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username.strip()
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = int(read_timeout or timeout)
        self.connect_timeout = int(connect_timeout or 10)
        self.read_timeout = int(read_timeout or timeout)
        self.keepalive_sec = int(keepalive_sec or 0)
        self.preferred_mode = (preferred_mode or "auto").lower()
        self.login_max_attempts = max(1, int(login_max_attempts))
        self.login_backoff_sec = float(login_backoff_sec)

        self.auth_mode: str = ""  # 当前生效：session | basic
        self.token: Optional[str] = None
        self.session_id: Optional[str] = None
        self._last_login_ts: float = 0.0

    def _timeout_tuple(self) -> Tuple[int, int]:
        return (self.connect_timeout, self.read_timeout)

    def log_connection_context(self, config_source: str = "") -> None:
        log.info("========== BMC 登录诊断 ==========")
        if config_source:
            log.info("配置来源: %s", config_source)
        log.info("目标地址: %s", mask_url(self.base_url))
        log.info("用户名: %s", self.username or "(空)")
        log.info("密码状态: %s", password_hint(self.password))
        log.info("认证策略: %s (auto=Session优先,失败则Basic)", self.preferred_mode)
        log.info("SSL 校验: %s", "开启" if self.verify_ssl else "关闭(自签名)")

    def _try_session_login(self) -> LoginResult:
        url = f"{self.base_url}/redfish/v1/SessionService/Sessions"
        payload = {"UserName": self.username, "Password": self.password}
        headers = {"Content-Type": "application/json"}
        log.info("尝试认证方式: Redfish Session (POST %s)", "/redfish/v1/SessionService/Sessions")
        try:
            r = requests.post(
                url,
                json=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=self._timeout_tuple(),
            )
        except requests.RequestException as exc:
            return LoginResult(
                ok=False,
                auth_mode="session",
                message=f"Session 请求网络异常: {exc}",
                detail=str(exc),
            )

        if r.status_code in (200, 201):
            token = r.headers.get("X-Auth-Token") or r.headers.get("x-auth-token")
            loc = r.headers.get("Location", "")
            sid = loc.rstrip("/").split("/")[-1] if loc else (r.json() or {}).get("Id")
            if not token:
                return LoginResult(
                    ok=False,
                    auth_mode="session",
                    status_code=r.status_code,
                    message="Session 已创建但响应缺少 X-Auth-Token 头",
                    detail=r.text[:300],
                )
            self.token = token
            self.session_id = sid
            self.auth_mode = "session"
            self._last_login_ts = time.time()
            return LoginResult(
                ok=True,
                auth_mode="session",
                session_id=sid,
                token=token,
                status_code=r.status_code,
                message="Session 登录成功",
            )

        hint = _http_status_hint(r.status_code, r.text)
        log.warning("Session 登录失败 HTTP %s — %s", r.status_code, hint)
        return LoginResult(
            ok=False,
            auth_mode="session",
            status_code=r.status_code,
            message=f"Session 登录失败 HTTP {r.status_code}",
            detail=hint,
        )

    def _try_basic_verify(self) -> LoginResult:
        url = f"{self.base_url}/redfish/v1/"
        log.info("尝试认证方式: HTTP Basic Auth (GET /redfish/v1/)")
        try:
            r = requests.get(
                url,
                auth=HTTPBasicAuth(self.username, self.password),
                verify=self.verify_ssl,
                timeout=self._timeout_tuple(),
            )
        except requests.RequestException as exc:
            return LoginResult(
                ok=False,
                auth_mode="basic",
                message=f"Basic Auth 请求网络异常: {exc}",
                detail=str(exc),
            )

        if r.status_code == 200:
            self.auth_mode = "basic"
            self.token = None
            self.session_id = None
            self._last_login_ts = time.time()
            ver = (r.json() or {}).get("RedfishVersion", "")
            return LoginResult(
                ok=True,
                auth_mode="basic",
                status_code=200,
                message=f"Basic Auth 验证成功 (Redfish {ver})".strip(),
            )

        hint = _http_status_hint(r.status_code, r.text)
        log.warning("Basic Auth 失败 HTTP %s — %s", r.status_code, hint)
        return LoginResult(
            ok=False,
            auth_mode="basic",
            status_code=r.status_code,
            message=f"Basic Auth 失败 HTTP {r.status_code}",
            detail=hint,
        )

    def login_with_retry(self, config_source: str = "") -> LoginResult:
        """带重试的登录；不抛异常，返回 LoginResult。"""
        self.log_connection_context(config_source)
        last: Optional[LoginResult] = None

        for attempt in range(1, self.login_max_attempts + 1):
            log.info("—— 登录第 %s/%s 次 ——", attempt, self.login_max_attempts)

            modes: list[str]
            if self.preferred_mode == "session":
                modes = ["session"]
            elif self.preferred_mode == "basic":
                modes = ["basic"]
            else:
                modes = ["session", "basic"]

            for mode in modes:
                result = self._try_session_login() if mode == "session" else self._try_basic_verify()
                last = result
                if result.ok:
                    log.info(
                        "[OK] 登录成功 | 方式=%s | session_id=%s",
                        result.auth_mode,
                        result.session_id or "N/A(Basic)",
                    )
                    result.attempts = attempt
                    return result

            if attempt < self.login_max_attempts:
                wait = self.login_backoff_sec ** (attempt - 1)
                log.warning("本轮登录均未成功，%.1fs 后重试…", wait)
                time.sleep(wait)

        assert last is not None
        last.attempts = self.login_max_attempts
        last.message = _build_final_message(last, self)
        log.error("[FAIL] 登录最终失败: %s", last.message)
        return last

    def login(self) -> Tuple[str, str]:
        """兼容旧接口；失败时抛 AuthError。"""
        from core.exceptions import AuthError

        r = self.login_with_retry()
        if not r.ok:
            raise AuthError(r.message)
        return r.token or "", r.session_id or ""

    def force_relogin(self) -> LoginResult:
        self.token = None
        self.session_id = None
        self.auth_mode = ""
        return self.login_with_retry()

    def ensure_valid_session(self) -> None:
        if self.auth_mode == "basic":
            if self.keepalive_sec <= 0:
                return
            if time.time() - self._last_login_ts >= self.keepalive_sec:
                log.info("Basic 模式保活：重新验证")
                self._try_basic_verify()
            return

        if self.keepalive_sec <= 0:
            return
        if not self.token:
            self.login_with_retry()
            return
        if time.time() - self._last_login_ts >= self.keepalive_sec:
            log.info("Session 保活：重新登录 (keepalive=%ss)", self.keepalive_sec)
            self.force_relogin()

    def auth_headers(self) -> dict:
        if self.auth_mode == "basic":
            return {"Content-Type": "application/json"}
        if not self.token:
            self.login_with_retry()
        if self.token:
            return {"X-Auth-Token": self.token, "Content-Type": "application/json"}
        return {"Content-Type": "application/json"}

    def get_requests_auth(self) -> Optional[HTTPBasicAuth]:
        if self.auth_mode == "basic":
            return HTTPBasicAuth(self.username, self.password)
        return None


def _http_status_hint(status: int, body: str) -> str:
    body_l = (body or "").lower()
    if status == 401:
        if "password" in body_l or "credential" in body_l:
            return "用户名或密码错误 (401 Unauthorized)"
        return "未授权 (401)，请检查账号权限或认证方式"
    if status == 403:
        return "禁止访问 (403)，账号可能无 Session 创建权限"
    if status == 503:
        return "BMC 服务暂不可用 (503)"
    if status == 0:
        return "无响应"
    return (body or "")[:200]


def _build_final_message(last: LoginResult, sm: SessionManager) -> str:
    lines = [
        f"登录失败（已重试 {sm.login_max_attempts} 次）",
        f"最后状态码: {last.status_code or 'N/A'}",
        f"最后方式: {last.auth_mode or 'session/basic'}",
        last.detail or last.message,
        "",
        "排查建议:",
        "  1) 确认 config/config.ini 中 password 不是 change_me（或复制 config.yaml 凭证）",
        "  2) 设置环境变量 BMC_PASS=你的密码 覆盖配置",
        "  3) 在 config.ini [basic] 设置 auth_mode = basic 或 auto",
        "  4) 浏览器访问 BMC Web 确认 ADMIN 账号可用",
        "  5) 检查带外网是否可达: Test-NetConnection <IP> -Port 443",
    ]
    if sm.password in PLACEHOLDER_PASSWORDS or not sm.password:
        lines.insert(1, "[WARN] 当前密码为占位符或为空，请修改 config/config.ini 或 config/config.yaml")
    return "\n".join(lines)


def print_login_failure(result: LoginResult) -> None:
    print("\n" + "=" * 50)
    print("BMC 登录失败")
    print("=" * 50)
    print(result.message)
    print("=" * 50 + "\n")
