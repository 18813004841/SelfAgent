---
name: selfagent-architecture
description: 整理和维护 SelfAgent 仓库架构。用于新增或调整模块、服务、目录、跨模块依赖、启动入口、端口、数据路径和架构文档，或开发前确认代码归属与架构约束时使用。
---

# SelfAgent 架构维护

用于判断功能归属、维护仓库架构文档和约束跨模块变更。先读取：

- `AGENTS.md`
- `docs/architecture/架构总览.md`
- `docs/architecture/模块边界.md`
- `docs/architecture/架构维护流程.md`

先核对当前代码，再修改文档或实现。文档中的待确认事项不能改写成已确认规则。

## 路由

- 工作台实现继续读取 `workbench/machine-dashboard-server/AGENTS.md` 和 `WORKBENCH_DEVELOPMENT_RULES.md`。
- 工作台页面、页面脚本或 `src/view` 继续执行 `skills/workbench-ui-flow/SKILL.md`。
- 修改机器控制、代码检查或智能体内部实现时，以该模块 README 和代码入口为准；只有仓库级边界变化时才更新架构文档。

## 变更要求

1. 找出现有入口、调用方、配置、存储和验证方式。
2. 选择现有运行单元；只有边界确实无法容纳时才提出新模块。
3. 保持工作台为编排层，独立工具和智能体拥有自己的入口与依赖。
4. 同步修改受影响的架构文档和模块规则，删除失效链接与过期约定。
5. 检查导入、路由注册、启动器注册、页面登记、默认端口、路径和文档链接。
