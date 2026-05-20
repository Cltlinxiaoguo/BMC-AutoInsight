"""Redfish HTTP 客户端：Session / Basic 双模式、401 刷新、退避重试。"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional, Tuple, Union

import requests

from core.auth import SessionManager
from core.exceptions import RedfishError

log = logging.getLogger("bmc_autoinsight")

TimeoutLike = Union[float, Tuple[float, float]]


class RedfishClient:
    def __init__(
        self,
        session: SessionManager,
        max_retries: int = 3,
        retry_cfg: Optional[Dict[str, Any]] = None,
    ):
        self.session = session
        self.max_retries = int(retry_cfg.get("max_attempts", max_retries)) if retry_cfg else max_retries
        self.retry_cfg = retry_cfg or {}

    def _timeouts(self, override: Optional[TimeoutLike]) -> TimeoutLike:
        if override is not None:
            return override
        ct = float(getattr(self.session, "connect_timeout", 10) or 10)
        rt = float(getattr(self.session, "read_timeout", 120) or 120)
        return (ct, rt)

    def request(self, method: str, path: str, timeout: Optional[TimeoutLike] = None, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.session.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if kwargs.pop("auth_refresh", True):
            self.session.ensure_valid_session()
        headers.update(self.session.auth_headers())
        http_auth = self.session.get_requests_auth()
        last_exc: Optional[Exception] = None
        max_retries = self.max_retries

        for attempt in range(max_retries + 1):
            try:
                to = self._timeouts(timeout)
                r = requests.request(
                    method,
                    url,
                    headers=headers,
                    auth=http_auth,
                    verify=self.session.verify_ssl,
                    timeout=to,
                    **kwargs,
                )
                if r.status_code == 401 and attempt < max_retries:
                    log.warning("[%s] 401，刷新认证后重试 (%s/%s)", path, attempt + 1, max_retries)
                    rel = self.session.force_relogin()
                    if rel.ok:
                        headers.update(self.session.auth_headers())
                        http_auth = self.session.get_requests_auth()
                    continue
                if r.status_code == 503 and attempt < max_retries:
                    wait = float(self.retry_cfg.get("backoff_base_sec", 2)) ** attempt
                    log.warning("[%s] 503，%.1fs 后重试", path, wait)
                    time.sleep(wait)
                    continue
                if r.status_code == 429 and self.retry_cfg.get("retry_429", True) and attempt < max_retries:
                    wait = float(self.retry_cfg.get("backoff_base_sec", 2)) ** attempt + random.random()
                    log.warning("[%s] 429，%.1fs 后重试", path, wait)
                    time.sleep(wait)
                    continue
                return r
            except requests.RequestException as e:
                last_exc = e
                if attempt < max_retries:
                    wait = 1.0 * (attempt + 1)
                    log.warning("[%s] 网络异常 %s，%.1fs 后重试", path, e, wait)
                    time.sleep(wait)
                    continue
                log.error("[%s] 网络请求失败: %s", path, e)
                raise RedfishError(str(e)) from e
        raise RedfishError(f"请求失败: {method} {path} ({last_exc})")

    def get_json(self, path: str, optional: bool = False, timeout: Optional[TimeoutLike] = None) -> Dict[str, Any]:
        r = self.request("GET", path, timeout=timeout)
        if r.status_code >= 400:
            if optional:
                log.warning("GET %s -> %s (已跳过)", path, r.status_code)
                return {"_skipped": True, "_status": r.status_code, "_path": path}
            raise RedfishError(f"GET {path} -> {r.status_code}")
        return r.json() if r.text else {}
