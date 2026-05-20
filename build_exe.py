"""一键调用 PyInstaller 打包 Windows 单文件 exe。

完整命令行（等价于本脚本）::

  pyinstaller --noconfirm --clean --onefile --console --name BMC-AutoInsight ^
    --hidden-import yaml --hidden-import jinja2 --hidden-import openpyxl --hidden-import configparser ^
    --add-data "config;config" --add-data "api_test/cases;api_test/cases" ^
    --add-data "tests/fixtures/redfish_responses;tests/fixtures/redfish_responses" ^
    main.py
"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    sep = ";" if platform.system() == "Windows" else ":"
    adds = [
        f"{ROOT / 'config'}{sep}config",
        f"{ROOT / 'api_test' / 'cases'}{sep}api_test/cases",
        f"{ROOT / 'tests' / 'fixtures' / 'redfish_responses'}{sep}tests/fixtures/redfish_responses",
    ]
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ROOT / "main.py"),
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name=BMC-AutoInsight",
        "--hidden-import=yaml",
        "--hidden-import=jinja2",
        "--hidden-import=openpyxl",
        "--hidden-import=configparser",
    ]
    for item in adds:
        cmd.extend(["--add-data", item])
    print("执行:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    print("完成: dist/BMC-AutoInsight.exe (Windows) 或 dist/BMC-AutoInsight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
