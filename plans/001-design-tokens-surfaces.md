# 001 — 建立共享颜色与表面系统

状态：Open  
规则：detector B-1（red，重复命中 `app.css` 多处）；E-3/E-8（orange）；人工判断 `US-004`（未绑定验证）。  
阻塞：`TOUCHES-DS`。设计系统源文件是 `workbench/machine-dashboard-server/web/assets/css/app.css`；没有发现独立 token 文件。

## 问题

`app.css` 从第 9 行起直接散落原始颜色值，例如 `color: #17212f`、`background: #f3f6fa`、`#10233f`、`#2f80ed`、`#fff`，并在 `.card`、`.collapse`、`.manage-entry:hover`、`.schedule-card:hover` 中分别写阴影。相同语义没有统一命名，边框和阴影同时存在，导致页面表面层级不稳定。

## 目标

在 `app.css` 顶部增加唯一的 `:root` 语义 token 层，至少覆盖：页面背景、主文字、次文字、侧栏背景/边框/悬停、表面背景/边框、主色/主色悬停、成功/失败背景与文字、焦点环、`surface-shadow-card`、`surface-shadow-popover`。把现有声明逐一替换为 token，不新增第二套颜色变量或直接 hex。

保留现有深蓝侧栏、浅灰页面背景、蓝色主按钮的产品语义；仅统一来源。`.card` 选择“边框或阴影”中的一种作为默认层级，并为浮层/悬停保留独立 elevation token；不要改变卡片尺寸、路由或业务状态。

## 仓库约定

共享页面样式全部位于 `workbench/machine-dashboard-server/web/assets/css/app.css`，页面通过 `/assets/css/app.css?v=18` 加载；沿用该单文件源，不创建根目录公共层。

## 步骤

1. 在 `app.css` 顶部建立 `:root` 语义 token，值从当前实际颜色映射而来。
2. 用 token 替换所有 CSS 中的 raw hex；检查压缩写法（如用户表格区域）和 rgba 阴影也一并归入语义 token。
3. 将 `.card`、`.collapse`、`.manage-entry:hover`、`.schedule-card:hover` 的阴影改用 token；维持现有视觉强弱和 hover 行为。
4. 为 token 命名写一段注释，说明 token 是工作台共享源；不要加入页面专用 token。

## 范围边界

不要改 HTML 结构、接口、页面文案、侧栏宽度、响应式断点或业务状态颜色含义。不要把 token 拆到新的公共目录。

## 验证

- `rg -n '#[0-9a-fA-F]{3,8}|rgba?\(' workbench/machine-dashboard-server/web/assets/css/app.css` 只允许出现在 token 定义中。
- 逐页打开 `overview`、`scheduler`、`manage`、`code-review`、`users`，核对页面背景、卡片、侧栏、主按钮、成功/失败状态和 hover 的 computed style。
- 对比折叠侧栏、卡片 hover、调度卡片 focus 前后，确保状态和布局没有跳变。
- 检查 token 实际被调用，而不是只存在未使用变量。
