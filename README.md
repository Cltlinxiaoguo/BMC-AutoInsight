# BMC AutoInsight

基于 **Redfish** 的 BMC 带外巡检、硬件/固件信息采集、规则告警、API 冒烟与**受控远程电源**的一体化 CLI 工具。面向 **运维工程师、测试工程师、交付验收** 场景，默认强调安全（二次确认、`dry_run`），报告可导出 HTML / JSON / TXT / Excel。

---

## 核心功能一览

| 模块 | 能力 |
|------|------|
| **巡检** | 单机 `inspect`：系统、散热、功耗、存储（受限时标注）、事件日志探测、传感器友好展示 |
| **告警** | `fault-check`：阈值规则（温度、风扇、内存、磁盘、RAID、PSU 等） |
| **硬件与固件** | `hardware-info`：型号/序列号/制造商、BIOS、BMC 固件、CPU、内存、硬盘、主板信息 |
| **API 冒烟** | `api-test`：自动发现可 GET 的 OData 路径，校验连通性与 HTTP 200 |
| **电源** | `power-status` / `power-on` / `power-off` / `power-restart`（变更类须确认，`dry_run` 可禁用真实下发） |
| **批量** | `batch-inspect`：CSV 多 BMC 巡检汇总 |
| **验证** | `login-test`、`--mock demo` 本地夹具全流程（无需真实 BMC） |

更多子命令的参数与示例见：**[doc/常用命令.md](doc/常用命令.md)**。

---

## 环境依赖

| 项 | 要求 |
|----|------|
| **操作系统** | Windows 10/11、Linux x64（主流发行版均可） |
| **Python** | **3.10+**（推荐 3.10～3.12） |
| **网络** | 运维终端能访问 BMC 带外 HTTPS（默认 443）；防火墙放行 |
| **Python 依赖** | 见根目录 **`requirements.txt`** |

主要第三方库：**`requests`、`urllib3`、`PyYAML`、`Jinja2`、`openpyxl`**（Excel）；开发与打包另含 **`pytest`、`pyinstaller`**。

---

## 部署与使用说明

### 方式一：企业工程师源码部署运行（正式推荐）

适合生产/准生产机房、审计留痕、可自行改配置与阈值、接入 CI。

1. **获取源码**

   ```bash
   git clone <你的仓库 URL> BMC-AutoInsight
   cd BMC-AutoInsight
   ```

2. **创建虚拟环境（推荐）**

   ```powershell
   # Windows PowerShell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **安装依赖**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

   > 若仅需运行工具而不跑测试，可只安装运行时依赖：`pip install requests urllib3 PyYAML Jinja2 openpyxl`。

4. **配置文件（勿提交密钥到 GitHub）**

   ```powershell
   copy config\config.ini.example config\config.ini
   # 按需复制阈值示例：
   copy config\thresholds.yaml.example config\thresholds.yaml
   ```

   编辑 **`config/config.ini`**：填写 `host`、`username`、`password`，按需调整超时、`verify_ssl`、`auth_mode`、`[power]` 等。  
   也可使用 **`config/config.yaml`**（与 INI 合并策略见下文「配置文件说明」）。

5. **验证登录**

   ```bash
   python main.py login-test
   ```

6. **执行巡检（示例）**

   ```bash
   python main.py inspect
   python main.py fault-check --exports json,html,txt,xlsx
   python main.py hardware-info
   python main.py api-test
   python main.py power-status
   ```

7. **运行自动化测试（可选）**

   ```bash
   pytest tests/ -q
   ```

8. **查看帮助**

   ```bash
   python main.py --help
   python main.py inspect --help
   ```

---

### 方式二：普通用户打包 exe 离线使用（备用）

适合无法安装 Python、仅需固定版本可执行文件的终端；**可执行文件由使用方在本机编译生成，仓库不向 GitHub 提交 `.exe`。**

1. 在已安装 Python 的机器上克隆源码并完成 **方式一** 中虚拟环境与 `pip install -r requirements.txt`。
2. 使用仓库提供的打包脚本：

   ```bash
   python build_exe.py
   ```

3. 在 **`dist/`** 下生成单文件 **`BMC-AutoInsight`**（Windows 扩展名为 `.exe`）。将 **`config/`** 中的 **`config.ini`（由示例复制）与 exe 一并分发到目标机，并保持相对路径或按脚本内说明放置。

4. **安全提示**：分发包勿内含真实密码；生产环境仍建议源码部署便于审计。

---

## 配置文件说明

| 路径 | 作用 |
|------|------|
| **`config/config.ini`** | 主配置：BMC 地址与账号、`verify_ssl`、超时、`auth_mode`、`logging`、`power`、`retry`、`threshold` 等（从 **`config.ini.example`** 复制） |
| **`config/config.yaml`** | 可选；可与 INI 合并（如 INI 中密码为占位符时从 YAML 补全 BMC 字段），详见 `core/config_loader.py` |
| **`config/thresholds.yaml`** | 可选告警阈值覆盖（复制 **`thresholds.yaml.example`**） |
| **`api_test/cases/smoke.yaml`** | API 冒烟手工用例，与自动发现路径合并 |

**敏感信息**：`config.ini`、`config.yaml`、`thresholds.yaml` 若在本地填入真实口令，已由 **`.gitignore`** 排除，请勿手工强制提交。

**环境变量**（可选用，避免明文落盘）：`BMC_HOST`、`BMC_USER`、`BMC_PASS`、`BMC_PORT` 等（以 `config_loader` 与环境变量映射为准）。

---

## 常用命令一览

以下为高频命令速查；**每条命令的功能、示例与详细说明见 [doc/常用命令.md](doc/常用命令.md)**。

| 命令 | 功能摘要 |
|------|----------|
| `python main.py --help` | 全局与子命令帮助 |
| `python main.py login-test` | 验证 BMC 登录（Session / Basic） |
| `python main.py inspect [--exports …]` | 单机全量巡检 + 硬件信息与 API 冒烟写入报告 |
| `python main.py fault-check [--exports …]` | 巡检 + 规则告警 + 报告 |
| `python main.py hardware-info [--exports …] [--max-paths N]` | 硬件/固件查询 + 附带 API 冒烟 |
| `python main.py api-test [--max-paths N]` | 仅 API 冒烟，独立 api_smoke 报告 |
| `python main.py batch-inspect -f <.csv> [--exports …]` | CSV 批量多机 |
| `python main.py power-status` | 只读电源状态 |
| `power-on` / `power-off` / `power-restart` | 变更类必须 `--confirm`；真实下发常需 `--execute` 或关闭 `dry_run` |
| `python main.py --mock demo` | **注意：`--mock` 必须写在子命令前**——Mock 全流程与报告 |

**传感器展示规则**：主机 `PowerState=Off` 且无读数时显示「【服务器关机，传感器无数据】」；`On` 且无读数时显示「【该传感器未上报数据】」。

---

## 输出报告说明

| 类型 | 说明 |
|------|------|
| **输出目录** | 默认 **`reports/`** |
| **命名** | 通常带时间戳前缀，如 `inspect_YYYYMMDD_HHMMSS.*`、`hardware_*`、`api_smoke_*` |
| **格式** | `json`、`html`、`txt`、`xlsx`（由 `--exports` 控制；Excel 依赖 `openpyxl`） |
| **HTML 常见章节** | 异常说明、存储/事件模块状态、温湿度与功耗摘要、硬件信息表、API 冒烟表、系统 JSON 等 |
| **Excel** | 多 Sheet：概要、告警、Thermal、Fans、Power、Modules、Hardware/CPU/Memory/Disk、API_Smoke 等（依命令与数据可用性略有差异） |

代码中的报告实现在 **`reports/exporter.py`**；运行时生成的 **`reports/` 下的 html/json/xlsx/txt** 已通过 **`.gitignore`** 忽略，便于仓库干净。

---

## 安全机制介绍

| 机制 | 说明 |
|------|------|
| **HTTPS 校验** | `verify_ssl=false` 用于自签名 BMC，控制台可能抑制告警；生产建议导入 BMC 可信根证书并设为 `true` |
| **认证** | 支持 Session 优先、Basic 回退（`auth_mode` 可配置） |
| **电源变更** | 默认 **`[power] dry_run = true`**；变更类命令强制 **`--confirm`**，可按配置要求双重确认 |
| **真实下发** | 在 `dry_run` 仍为 true 时，需 **`--execute`**（与 `--confirm` 同用）才会向 BMC 下发电源指令——以当前实现与配置为准 |
| **凭据管理** | 密码勿提交仓库；推荐使用环境变量或企业密钥管理 |

---

## GitHub / 源码托管提交规范（重要）

**请仅推送以下内容：**

- 全部 **Python 源码**、**测试**、`api_test/` 下 YAML **用例**  
- **`config/*.example`、`config/*.csv` 示例**（无真实密钥）  
- **`doc/` 文档**、根目录 **`README.md`**、**`requirements.txt`**、**`.gitignore`**  
- **`build_exe.py`** 等打包脚本（不含生成物）

**请不要推送：**

- **`dist/`、`build/`、`.exe`、`*.spec` 等打包产物**  
- **`config/config.ini`、`config/config.yaml`、本地 `thresholds.yaml`（若含敏感信息）**  
- **`reports/` 下巡检生成的 html/json/xlsx/txt**  
- **`logs/`**  

项目结构保持现有模块划分；详情请见文末「仓库目录结构」。

---

## 更多文档

- [doc/项目介绍.md](doc/项目介绍.md) — 开源导读与文档索引  
- [doc/常用命令.md](doc/常用命令.md) — 命令详解  
- [doc/BMC-AutoInsight_需求与设计.md](doc/BMC-AutoInsight_需求与设计.md)  
- [doc/BMC-AutoInsight_测试用例与自动化.md](doc/BMC-AutoInsight_测试用例与自动化.md)  

---

## 许可证与免责声明

若仓库根目录附有 `LICENSE` 则以该文件为准。使用本工具对 BMC 下发的任何操作（尤其电源变更）应由具备权限的人员执行；作者与贡献者不对误操作造成的损失承担责任。

---

## 附录：仓库目录结构（概要）

下列为典型开源仓库布局；实际以您克隆后的文件为准。**`reports/` 与 `logs/` 为运行时生成，`config` 中非示例文件不落库。**

```
BMC-AutoInsight/
├── README.md                 # 本文件
├── requirements.txt          # Python 依赖
├── .gitignore
├── main.py                   # CLI 入口
├── build_exe.py              # （可选）PyInstaller 封装脚本
├── api_test/                 # API 冒烟：发现、运行、YAML 用例与导出
├── config/                   # 配置示例与批量 CSV 样例（敏感文件不入库）
├── control/                  # 电源控制
├── core/                     # 配置、会话、客户端、日志、模型等
├── doc/                      # 常用命令、项目介绍、设计与测试文档
├── fault_detect/             # 规则引擎与各规则模块
├── monitor/                  # 采集编排、散热、电源、存储、事件、硬件信息等
├── reports/                  # 报告模块（exporter.py、jinja2_inline.py 等）+ 运行时输出（*.html/json/xlsx/txt 已 .gitignore）
├── tests/                    # pytest 与 Redfish fixture
└── logs/                     # 运行日志目录（运行时创建，.gitignore）
```

---

*欢迎使用并提交 Issue / Pull Request。*
