"""统一配置加载：config.ini > config.yaml > config.ini.example，自动合并凭证。"""
from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from core.auth import PLACEHOLDER_PASSWORDS
from core.exceptions import ConfigError

_ENV_KEYS = (
    ("BMC_HOST", ["basic", "host"]),
    ("BMC_USER", ["basic", "username"]),
    ("BMC_PASS", ["basic", "password"]),
    ("BMC_PORT", ["basic", "port"]),
)


def _read_ini(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")
    cp.read(path, encoding="utf-8")
    return cp


def ini_to_nested(cp: configparser.ConfigParser) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for sec in cp.sections():
        out[sec.lower()] = dict(cp.items(sec))
    return out


def _coerce_types(cfg: Dict[str, Any]) -> Dict[str, Any]:
    def _bool(v: Any, default: bool = False) -> bool:
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
        return default

    basic = cfg.get("basic") or {}
    for k in (
        "port",
        "connect_timeout",
        "read_timeout",
        "inspection_timeout",
        "session_keepalive_sec",
        "max_retries",
        "login_attempts",
    ):
        if k in basic and basic[k] is not None and str(basic[k]).strip() != "":
            try:
                basic[k] = int(str(basic[k]).strip())
            except ValueError:
                pass
    for k in ("verify_ssl", "enable_batch", "power_require_double_confirm"):
        if k in basic:
            basic[k] = _bool(basic.get(k), False)
    cfg["basic"] = basic

    thr = cfg.get("threshold") or {}
    for k in list(thr.keys()):
        if thr[k] is None or str(thr[k]).strip() == "":
            continue
        try:
            thr[k] = float(str(thr[k]).strip())
        except ValueError:
            pass
    cfg["threshold"] = thr

    pwr = cfg.get("power") or {}
    for k in ("dry_run", "require_confirm", "require_double_confirm"):
        if k in pwr:
            pwr[k] = _bool(pwr.get(k), k != "dry_run")
    cfg["power"] = pwr

    retr = cfg.get("retry") or {}
    for k in ("max_attempts", "backoff_base_sec", "login_attempts"):
        if k in retr and str(retr[k]).strip() != "":
            try:
                retr[k] = int(str(retr[k]).strip())
            except ValueError:
                pass
    if "retry_429" in retr:
        retr["retry_429"] = _bool(retr.get("retry_429"), True)
    cfg["retry"] = retr
    return cfg


def load_yaml_bmc(root: Path) -> Dict[str, Any] | None:
    p = root / "config" / "config.yaml"
    if not p.exists():
        return None
    try:
        import yaml

        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    b = raw.get("bmc") or {}
    return {
        "host": b.get("host") or "127.0.0.1",
        "username": b.get("username", "admin"),
        "password": b.get("password", ""),
        "verify_ssl": b.get("verify_ssl", False),
        "read_timeout": int(b.get("timeout") or b.get("read_timeout") or 120),
        "connect_timeout": int(b.get("connect_timeout") or 10),
        "port": b.get("port"),
    }


def _merge_sections_from_example(nested: Dict[str, Any], root: Path) -> None:
    ex = root / "config" / "config.ini.example"
    if not ex.exists():
        return
    ex_nested = ini_to_nested(_read_ini(ex))
    for sec in ("threshold", "logging", "power", "retry"):
        if sec not in nested and sec in ex_nested:
            nested[sec] = ex_nested[sec]
    basic = nested.setdefault("basic", {})
    ex_basic = ex_nested.get("basic") or {}
    for k in (
        "auth_mode",
        "connect_timeout",
        "read_timeout",
        "inspection_timeout",
        "session_keepalive_sec",
        "port",
    ):
        if k not in basic and k in ex_basic:
            basic[k] = ex_basic[k]


def _merge_yaml_credentials(nested: Dict[str, Any], root: Path) -> str:
    """若 ini 密码为占位符，从 config.yaml 合并 host/user/pass。"""
    note = ""
    basic = nested.setdefault("basic", {})
    pwd = str(basic.get("password", "")).strip()
    if pwd.lower() not in PLACEHOLDER_PASSWORDS and pwd:
        return note
    yaml_bmc = load_yaml_bmc(root)
    if not yaml_bmc:
        return note
    for k, v in yaml_bmc.items():
        if v is not None and str(v).strip() != "":
            basic[k] = v
    note = " + 已从 config/config.yaml 合并 BMC 凭证"
    return note


def _load_config_nested(root: Path) -> Tuple[Dict[str, Any], str]:
    ini_user = root / "config" / "config.ini"
    yaml_path = root / "config" / "config.yaml"
    ini_example = root / "config" / "config.ini.example"

    source = ""
    nested: Dict[str, Any]

    if ini_user.exists():
        nested = ini_to_nested(_read_ini(ini_user))
        source = str(ini_user.relative_to(root)) if ini_user.is_relative_to(root) else str(ini_user)
    elif yaml_path.exists():
        yaml_bmc = load_yaml_bmc(root)
        if not yaml_bmc:
            raise ConfigError("config/config.yaml 格式无效")
        nested = {"basic": dict(yaml_bmc)}
        _merge_sections_from_example(nested, root)
        raw_yaml = yaml_path.read_text(encoding="utf-8")
        try:
            import yaml

            y = yaml.safe_load(raw_yaml) or {}
            if y.get("logging"):
                nested["logging"] = y["logging"]
            if y.get("power"):
                nested["power"] = y["power"]
        except Exception:
            pass
        source = "config/config.yaml"
    elif ini_example.exists():
        nested = ini_to_nested(_read_ini(ini_example))
        source = "config/config.ini.example (请复制为 config.ini 或提供 config.yaml)"
    else:
        raise ConfigError("未找到 config/config.ini、config.yaml 或 config.ini.example")

    merge_note = _merge_yaml_credentials(nested, root)
    source += merge_note
    return nested, source


def _apply_env(cfg: Dict[str, Any]) -> None:
    basic = cfg.setdefault("basic", {})
    for env_name, path in _ENV_KEYS:
        val = os.environ.get(env_name)
        if val is not None and str(val).strip() != "":
            sec, opt = path
            cfg.setdefault(sec, {})[opt] = val.strip()


def _merge_yaml_thresholds(root: Path, cfg: Dict[str, Any]) -> None:
    yml = root / "config" / "thresholds.yaml"
    if not yml.exists():
        return
    try:
        import yaml

        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    except Exception:
        return
    flat: Dict[str, Any] = {}
    if isinstance(data.get("thermal"), dict):
        t = data["thermal"]
        flat["cpu_temp_warn_c"] = t.get("cpu_temp_warn_c")
        flat["cpu_temp_crit_c"] = t.get("cpu_temp_crit_c")
    if isinstance(data.get("fan"), dict):
        f = data["fan"]
        flat["fan_rpm_warn_min"] = f.get("min_rpm_warn")
        flat["fan_rpm_crit_min"] = f.get("min_rpm_crit")
    if isinstance(data.get("psu"), dict):
        flat["psu_input_volt_warn_min"] = data["psu"].get("min_input_voltage")
    thr = cfg.setdefault("threshold", {})
    for k, v in flat.items():
        if v is not None:
            thr[k] = v


def load_app_config(root: Path) -> Dict[str, Any]:
    nested, source = _load_config_nested(root)
    _coerce_types(nested)
    _apply_env(nested)
    _merge_yaml_thresholds(root, nested)

    basic = nested.get("basic") or {}
    nested["config_source"] = source
    nested["bmc"] = {
        "host": _host_with_port(basic),
        "username": basic.get("username", "admin"),
        "password": basic.get("password", ""),
        "verify_ssl": basic.get("verify_ssl", False),
        "timeout": int(basic.get("read_timeout") or 120),
        "connect_timeout": int(basic.get("connect_timeout") or 10),
        "read_timeout": int(basic.get("read_timeout") or 120),
        "inspection_timeout": int(basic.get("inspection_timeout") or 0),
        "session_keepalive_sec": int(basic.get("session_keepalive_sec") or 0),
        "system_id_override": (basic.get("system_id") or "").strip() or None,
        "chassis_id_override": (basic.get("chassis_id") or "").strip() or None,
        "auth_mode": (basic.get("auth_mode") or "auto").strip().lower(),
    }
    nested.setdefault("power", {})
    nested["power"].setdefault("dry_run", True)
    nested["power"].setdefault("require_confirm", True)
    nested["power"].setdefault(
        "require_double_confirm",
        bool(basic.get("power_require_double_confirm", True)),
    )
    return nested


def _host_with_port(basic: Dict[str, Any]) -> str:
    host = (basic.get("host") or "127.0.0.1").strip()
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    port = basic.get("port")
    if port and str(port) not in ("443", "80"):
        return f"https://{host}:{port}"
    return f"https://{host}"


def load_thresholds(root: Path) -> Dict[str, Any]:
    cfg = load_app_config(root)
    thr = cfg.get("threshold") or {}
    return {
        "thermal": {
            "cpu_temp_warn_c": thr.get("cpu_temp_warn_c", 75),
            "cpu_temp_crit_c": thr.get("cpu_temp_crit_c", 85),
        },
        "fan": {
            "min_rpm_warn": thr.get("fan_rpm_warn_min", 1500),
            "min_rpm_crit": thr.get("fan_rpm_crit_min", 800),
        },
        "psu": {"min_input_voltage": thr.get("psu_input_volt_warn_min", 200)},
        "power": {
            "watts_warn": thr.get("power_watts_warn", 800),
            "watts_crit": thr.get("power_watts_crit", 1200),
        },
    }


def load_yaml(path: Path) -> Dict[str, Any]:
    import yaml

    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"配置格式错误: {path}")
    return data
