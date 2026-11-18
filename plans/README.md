# 界面优化审计计划

审计范围：`workbench/machine-dashboard-server/web` 全部页面、共享样式与页面内联样式。

规则快照：`public-2026.11.06-1`，索引 checksum `2ff9cedd3abd8868acb8ea7c4fffa3b32cd6ed6971788ad3aca4a1a8d19ab78f`。

说明：本次使用 bundled detector 运行结果作为机器证据；未能运行 `canon-route.mjs`（当前环境未发现可用的 unslop 依赖副本），因此不宣称已完成 routed canon 的绑定验证。人工判断均标为 judgement。

## 执行顺序

1. [001-design-tokens-surfaces.md](001-design-tokens-surfaces.md) — 颜色与表面系统（TOUCHES-DS）— Open
2. [002-motion-accessibility.md](002-motion-accessibility.md) — 动效、焦点与可访问性 — Open
3. [003-typography-hierarchy.md](003-typography-hierarchy.md) — 字号、行高、标题层级 — Open
4. [004-inline-style-consolidation.md](004-inline-style-consolidation.md) — 内联样式收口 — Open

## 已检查且未形成计划

- 未发现需要新增图标库或替换现有图标集的证据。
- 未发现渐变、首屏动画或明显“功能卡片图标网格”的检测器结果。
- 页面路由和业务交互未在本审计中改变；视觉计划必须保留现有请求、轮询、登录和任务操作。

## 状态与提交记录

| 计划 | 状态 | 执行提交 |
| --- | --- | --- |
| 001 | Implemented in working tree | — |
| 002 | Implemented in working tree | — |
| 003 | Implemented in working tree | — |
| 004 | Partially implemented; remaining dynamic/layout inline styles reviewed | — |
