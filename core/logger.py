"""结构化日志：控制台 + 按日落盘到 logs/，敏感信息脱敏。"""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_SENSITIVE = re.compile(
    r'(Password|password|UserName|token|Token|Authorization)["\']?\s*[:=]\s*"?[^"\'\s,}]+',
    re.I,
)


class _MaskFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SENSITIVE.sub(r"\1=***", record.msg)
        return True


def setup_logging(level: str = "INFO", log_dir: str | Path = "logs") -> logging.Logger:
    root = logging.getLogger("bmc_autoinsight")
    if root.handlers:
        return root

    numeric = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.addFilter(_MaskFilter())

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fh = TimedRotatingFileHandler(
        Path(log_dir) / "bmc_insight.log",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    fh.addFilter(_MaskFilter())

    root.addHandler(sh)
    root.addHandler(fh)

    # 第三方库降噪
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    return root
