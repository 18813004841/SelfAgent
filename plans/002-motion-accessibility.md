# 002 — 补齐动效与键盘焦点反馈

状态：Open  
规则：detector G-9（orange）；J-9（orange）；人工判断 KR-13/KR-15/KR-16（未绑定验证）。

## 问题

`app.css` 含 `.schedule-card`、`.manage-entry` 等 transition/hover 动效，但全工程没有 `prefers-reduced-motion`。`.schedule-card:hover, .schedule-card:focus` 在第 256 行设置 `outline: 0`，没有对应的 `:focus-visible` 替代样式，键盘用户失去位置反馈。

## 目标

保留 hover 的边框、阴影和轻微位移；把键盘反馈限定到 `:focus-visible`，使用现有蓝色焦点语义并确保对比度。增加全局 reduced-motion 覆盖：减少 transition、animation 和平滑滚动，同时不阻断脚本驱动的必要滚动行为。

## 步骤

1. 将 `.schedule-card:hover, .schedule-card:focus` 拆为 hover 与 `:focus-visible` 规则；移除 `outline: 0`。
2. 为 `.schedule-card:focus-visible`、`.manage-entry:focus-visible`、侧栏按钮和 `.collapse` 增加可见 focus ring，复用共享焦点 token。
3. 在 `app.css` 末尾增加 `@media (prefers-reduced-motion: reduce)`，将 transition/animation duration 设为极短并移除 transform 位移；不要删除状态变化。
4. 保持 collapse、表单控件和任务卡片的原有点击/键盘语义。

## 范围边界

不改变路由、不新增动画库、不把所有 hover 状态删除、不修改后端轮询。

## 验证

- 键盘 Tab 依次操作侧栏、折叠按钮、调度卡片、表单控件，确认焦点始终可见。
- 使用 DevTools 模拟 `prefers-reduced-motion: reduce`，确认无明显位移/过渡，同时脚本滚动仍能完成。
- 检查鼠标 hover 与键盘 focus 的视觉职责不同且不会造成布局跳变。
