# 工作台客户机 Local Agent

当前版本为 `1.0.0`。包内 `VERSION` 记录版本，工作台设置页显示本机版本与服务端版本，并提供对应版本下载入口。升级时在旧客户端目录执行 `update-client.ps1 -PackagePath <新版ZIP> -DashboardUrl <工作台地址> -Start`；升级器会停止旧 Local Agent、保留旧目录为 `.previous`，失败时恢复旧目录。用户配置和数据目录位于 `%LOCALAPPDATA%\LocalWorkbench`，不会随包覆盖。

本项目运行在浏览工作台的客户机上，只监听 `127.0.0.1:18991`。中央客户端、本地 Codex、设置页的本地目录由它管理；中央服务、调度和其他业务留在服务端。它是工作台项目内的独立运行单元。

## 初始化与启动

也可从工作台“设置 → 下载本机客户端组件”取得 ZIP，在客户机解压后进入 `machine-dashboard-client` 目录运行初始化脚本。客户机仍需安装 Python 3.11 或更新版本；ZIP 不包含 Python、虚拟环境、用户配置或运行数据。

需要 Python 3.11 或更新版本；Agent 本身仅使用标准库，没有第三方运行依赖。以下命令在本目录执行：

```powershell
py -3.11 -m venv .venv
$env:WORKBENCH_DASHBOARD_URL = "http://工作台服务器地址:18888"
.\start-local-agent.bat
```

启动器固定使用本目录 `.venv/Scripts/python.exe`；可用 `WORKBENCH_CLIENT_PYTHON` 指定另一绝对解释器路径，不依赖终端激活环境。升级 Python 时先另建环境并运行隔离验证，再切换该变量。无需安装依赖；维护本项目的唯一依赖声明为 `pyproject.toml`。

`WORKBENCH_DASHBOARD_URL` 首次启动时可用于设置工作台来源。Local Agent 只允许工作台端口（默认 `18888`）的回环或局域网来源；当服务器更换为新的局域网 IP 后，用户直接打开新工作台页面即可自动更新本机信任来源。公网来源仍会被拒绝。未启动 Agent 时，页面应提示本机服务不可用，不回退到服务器路径。当前前端固定连接端口 18991；只修改 Agent 端口不会同步修改前端。

macOS 用户可双击 `start-local-agent.command` 一键启动；首次运行会自动创建 `.venv` 和用户配置。也可在终端执行 `./start-local-agent.sh`，或先设置 `WORKBENCH_DASHBOARD_URL` 后执行。需要安装 Python 3.11 或更新版本；如系统阻止脚本运行，请在“系统设置 → 隐私与安全性”中允许打开。

从 Safari 下载后首次运行若出现“来自互联网”或“没有正确的访问权限”，请先按包内 `MACOS-INSTALL.md` 执行一次 `xattr -dr com.apple.quarantine .` 和 `chmod +x`。这是 macOS 下载隔离机制，无法由 Windows 在 ZIP 中预先清除。

同一台电脑只能运行一个 `18991` Agent。若服务器地址改变，先停止旧 Agent，再执行初始化脚本或设置 `WORKBENCH_DASHBOARD_URL` 后重新启动；否则页面会显示来源不可信或端口已占用。

可使用 `powershell -ExecutionPolicy Bypass -File .\stop-local-agent.ps1` 停止本机 Agent。脚本会核对 PID 对应的命令行和端口，无法确认归属时拒绝操作。

局域网浏览器访问本机 Agent 时，Agent 会校验浏览器来源，并响应 Chromium Private Network Access 预检。每台客户机仍必须单独启动 Agent；服务器不会代理或读取客户机目录。

手动启动等价命令：

```powershell
.venv\Scripts\python.exe -m src.local_agent --dashboard-url http://工作台服务器地址:18888
```

本地 Codex 任务支持 `timeout_seconds`（1 到 86400 秒）以及 `POST /api/local-codex/task/cancel` 取消；提交和查询接口分别是 `POST/GET /api/local-codex/task`，任务终态会写回客户机自己的 SQLite 数据库。\n\n本地 Codex 还需要客户机自行安装 Codex CLI；中央客户端需要先在页面下载并安装 machine-control 客户端包。中央连接参数必须填写客户机可达的服务器地址。

## 数据与回滚

固定客户机配置为 `%LOCALAPPDATA%/LocalWorkbench/config/settings.json`；默认本地文件目录为 `%LOCALAPPDATA%/LocalWorkbench/client/storage`。`data` 保存客户机 Codex 任务库，`logs` 保存日志（HTTP 日志默认达到 5 MiB 时最多保留 3 个轮转文件；隔离测试可用 `WORKBENCH_LOCAL_AGENT_LOG_MAX_BYTES` 和 `WORKBENCH_LOCAL_AGENT_LOG_BACKUPS` 调低），`run` 保存 PID，`cache` 保存下载缓存。可通过 `WORKBENCH_CLIENT_DATA_DIR` 或 `--data-dir` 显式隔离数据。

如果已有 `settings.json` 缺少 `storage_dir`，首次启动会补写上述默认目录；已有非空目录配置保持不变。

客户端包升级保留 `central-client.previous`；确认前不要删除旧目录。回滚先停止本机 Worker，再交换当前包与备份目录。服务端旧 Codex 任务不会自动迁移到客户机，真实数据迁移仍未验收。

## 验证和已知限制

服务端部署前，在仓库根目录执行 `python workbench/machine-dashboard-client/scripts/build_package.py --output workbench/machine-dashboard-client/dist/workbench-machine-dashboard-client.zip`。服务端通过 `GET /api/local-agent/download` 提供该包；缺包时明确报错，不从其他项目取包。

```powershell
.venv\Scripts\python.exe scripts/validate_local_agent.py
```

仓库根目录执行 `python scripts/validate_client_setup.py` 可验证 Windows 客户机初始化脚本，包括默认目录、已有自定义目录保留以及非法工作台网址拒绝。此检查也包含在 `python scripts/validate_local.py` 中。

验证使用系统临时目录，覆盖来源拒绝、本地路径、合法包安装、路径穿越拒绝及端口关闭。真实远程浏览器、原生目录选择、Codex 完整进程树退出、长任务取消/超时、日志轮转和客户机数据库备份迁移尚未完成验收；隔离 HTTP 通过不代表这些业务已通过。当前请以前台运行和 Ctrl+C 退出，禁止凭 PID 文件结束未知进程。





局域网客户机初始化：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup-client.ps1 -DashboardUrl http://服务器地址:18888 -Start
```

脚本在当前客户机创建独立 `.venv`，固定写入 `%LOCALAPPDATA%\LocalWorkbench\config\settings.json`，默认目录为 `%LOCALAPPDATA%\LocalWorkbench\client\storage`，然后只监听 `127.0.0.1:18991`。每台客户机都要在自己的电脑执行一次；服务端不会替客户机创建或修改这些文件。
