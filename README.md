# SelfAgent

本仓库包含三个独立运行单元：

| 项目 | 位置 | 职责 |
| --- | --- | --- |
| 工作台 | `workbench/machine-dashboard-server/`、`workbench/machine-dashboard-client/` | 服务端 Web/API、调度和集成；客户机本地工具接入 |
| AiAgent | `AiAgent/` | 智能体源码、环境、配置与数据；当前 CLI/网关位于 `AiProject/Codes/Agents/OpenAiAgent/` |
| machine-control | `Tools/machine-control/` | 中央服务、Worker、共享协议和客户端打包 |

工作台通过 HTTP、CLI、协议和启动器集成独立项目。每个项目使用自己的虚拟环境与数据目录；开发前读取 [AGENTS.md](AGENTS.md) 和 [架构总览](docs/architecture/架构总览.md)。

远程访问时，中央客户端、本地 Codex 和设置中的本地路径由浏览器所在电脑上的 [Local Agent](workbench/machine-dashboard-client/README.md) 管理；其余功能仍由工作台服务端执行。

## 初始化与验证

需要 Python 3.11/3.12、Node.js 和 uv；具体版本、依赖及项目启动命令见 [环境与依赖治理](docs/architecture/环境与依赖治理.md) 和 [入口清单](docs/architecture/入口清单.md)。以下命令从仓库根目录执行：

```powershell
python scripts/bootstrap_projects.py --project all --verify
python scripts/validate_local.py
```

两个拥有 `uv.lock` 的项目可分别使用锁定安装：

```powershell
python scripts/bootstrap_projects.py --project machine-control --frozen --verify
python scripts/bootstrap_projects.py --project aiagent --frozen --verify
```

初始化会安装依赖到各项目 `.venv`；`--no-install` 只创建缺失环境。联网和缓存权限需由运行环境提供。MCP 可选依赖使用 `uv sync --locked --extra mcp` 安装，AiAgent 测试依赖使用 `uv sync --locked --extra test` 安装，均在对应项目目录执行。

## 架构与交付状态

- [现状审计](docs/architecture/审计报告.md)
- [目标架构与迁移映射](docs/architecture/目标架构与迁移映射.md)
- [持续维护与验证要求](docs/architecture/持续维护.md)
- [最终验收矩阵](docs/architecture/最终验收矩阵.md)
- [发布与回滚](docs/architecture/发布与回滚.md)

当前架构治理仍在进行中。`validate_local.py` 通过代表本地检查通过；真实浏览器、跨主机、正式用户数据迁移和发布回滚等验收以矩阵为准。不得直接删除旧数据或用 Git 重置回滚用户改动。
