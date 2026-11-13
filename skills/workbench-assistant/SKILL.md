---
name: workbench-assistant
description: 当前工程 machine-dashboard-server 的开发助手入口。处理工作台的 Python 服务、View 路由、调度器、HTML、JavaScript、配置、日志和启动脚本时使用；只在遵循该工程 AGENTS.md 的工作台目录内生效。
---

# 工作台开发助手

这是 workbench/machine-dashboard-server 的项目级开发入口。开始修改前必须读取：

- workbench/machine-dashboard-server/AGENTS.md
- workbench/machine-dashboard-server/WORKBENCH_DEVELOPMENT_RULES.md

先确认真实入口、路由、数据存储、调度器和现有实现，再动代码。把事实、计划变更和待确认事项分开记录。优先复用公共 Logger、存储、Router、进程管理和页面公共组件。

## 任务分流

- 涉及 HTML 控件、页面 JS、页面加载、fetch、配置回填、参数保存或 src/view 下的 view.py：读取并执行 E:/SelfAgent/skills/workbench-ui-flow/SKILL.md。
- 只涉及 Python 业务、调度、配置或进程：沿用项目规则，保持业务模块与 View/API 边界。
- 只涉及样式或静态资源：复用现有页面结构和公共样式，并确认页面加载入口。
- 涉及日志：使用现有 core.Log 工厂，禁止在业务代码中自行初始化 Logger。

## 开发闭环

1. 定义接口或行为契约：入口、参数、返回值、错误、刷新和持久化。
2. 搜索同类实现，确定应修改的真实文件。
3. 先实现后端和日志，再接前端调用；需要界面链路时遵循 workbench-ui-flow。
4. 处理空数据、加载中、重复触发、失败和停止条件。
5. 做语法或静态检查，并检查真实页面请求、路由注册、错误分支和 Git diff。

不要因为任务名称包含工作台就修改无关模块；只改完成用户目标所需的最小范围。
