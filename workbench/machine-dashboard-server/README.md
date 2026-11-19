# 本地机器工作台服务

## 目录结构

- `src/`：核心 Python 服务代码
- `web/`：工作台前端页面
- `config/`：配置模板和环境变量说明
- `logs/`：运行日志目录（默认不提交日志内容）
- `plugins/`：可选插件扩展目录
- `tools/`：运维和开发辅助工具
- `scripts/`：启动、检查等自动化脚本

## 启动

```bash
sh start.sh
```

macOS 用户可双击 `start-macos.command` 启动服务；首次使用前请安装 Python 3.11 或更新版本。也可在终端执行 `./start.sh`，并通过 `MACHINE_DASHBOARD_HOST`、`MACHINE_DASHBOARD_PORT` 覆盖监听地址和端口。

本机访问可用 `http://127.0.0.1:18888`；局域网用户使用服务端实际局域网地址，例如 `http://192.168.1.10:18888`。直接运行 `src/server.py` 默认监听 `0.0.0.0`，如需本机-only 部署可设置 `MACHINE_DASHBOARD_HOST=127.0.0.1`。

可通过 `MACHINE_DASHBOARD_PORT` 修改端口。
## 局域网访问与客户机配置

局域网部署使用 `一键启动.bat`，服务端监听 `0.0.0.0:18888`。其他电脑浏览器访问服务端实际局域网地址，例如 `http://192.168.1.10:18888`；每台客户机还需在本机运行 `workbench/machine-dashboard-client/setup-client.ps1 -DashboardUrl http://192.168.1.10:18888 -Start`。浏览器的目录选择、中央客户端和本地 Codex 请求均由该客户机的 `127.0.0.1:18991` Local Agent 执行，服务端不读取客户机路径。

部署前构建客户机下载包：`python workbench/machine-dashboard-client/scripts/build_package.py --output workbench/machine-dashboard-client/dist/workbench-machine-dashboard-client.zip`。用户可在设置页下载该包并在自己的电脑解压运行初始化脚本。
