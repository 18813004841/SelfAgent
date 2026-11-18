# 004 — 收口页面内联样式

状态：Open  
规则：detector B-7（white，多处）；人工判断 DEC-1（未绑定验证）。

## 问题

`login.html`、`register.html`、`settings.html`、`local-codex-task.html`、`openai-agent.html` 等页面把颜色、边框、背景、尺寸和布局写在 `style` 属性中。颜色内联直接绕过共享样式源，也使焦点、响应式和表面系统难以统一。

## 目标

把视觉属性迁移到 `app.css` 的语义类；保留真正动态的布局数值或由脚本控制的状态。页面 HTML 只保留结构、内容和必要的行为 hook。

## 步骤

1. 为登录/注册容器、设置目录行、Codex skill 菜单、OpenAiAgent 输入与结果区建立语义类。
2. 将内联颜色、背景、边框、阴影、圆角、字体和可复用布局声明移入 `app.css`，并复用计划 001 的 token。
3. 保留 `style="display:block;width:100%"` 等仅在确有动态/局部布局需要时的声明；优先改为类并逐个检查调用方。
4. 清理所有页面的颜色型内联样式，避免新增 `!important`。

## 范围边界

不改页面脚本选择器 id、不改接口、不把脚本运行时写入的动态 style 强行静态化。

## 验证

- `rg -n 'style=.*(#|rgb|white|black|background|border|box-shadow)' workbench/machine-dashboard-server/web/pages` 无结果，或每个保留项有明确动态理由。
- 登录、注册、设置、Codex 任务和 OpenAiAgent 页面在桌面/移动宽度下与迁移前结构一致。
- 复核键盘 focus、错误消息和弹出 skill 菜单层级未被 CSS 迁移破坏。
