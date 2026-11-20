# 工作台 HTML UI 资产清单与统一规范

> 目的：把当前工作台页面中的结构、控件和视觉基础整理成可检索的资产清单，为后续审美优化、主题换皮和组件统一提供依据。
>
> 盘点范围：`workbench/machine-dashboard-server/web/index.html`、`web/pages/*.html`、`web/assets/css/app.css`。页面实际通过 `web/assets/js/app.js` 动态加载，页面专属行为位于 `web/assets/js/pages/`。
>
> 口径：下表的“现状”来自代码扫描；“建议”是下一阶段统一规范，不代表已经完成改造。

## 1. 页面总览

| 页面 | 主要模块 | 控件概况 | 结构/容器 |
| --- | --- | --- | --- |
| overview | 本机概览、状态统计 | 刷新状态 | card、stats |
| scheduler | 调度器服务、任务列表、新增任务 | 启动/关闭、新增、创建、取消；文本框、时间、选择框 | card、schedule-board/grid |
| tasks | 任务列表占位 | 无静态按钮 | card |
| server-maintenance | 服务器维护输入区 | 重启、发送、取消；文本域 | card |
| frontend | 前端模块入口 | 模块磁贴（整体可点击） | frontend-hero、module-grid、module-tile |
| package-error-analysis | 分析任务列表 | 返回、创建新任务 | package-header、analysis-task-list、analysis-empty |
| package-error-analysis-task | 分析输入、输出、流程 | 返回、开始分析、结束任务；文本域 | analysis-workspace、analysis-left、analysis-output、analysis-progress |
| store | 商城首页、皮肤模块入口 | 皮肤商城入口 | frontend-hero、module-grid、module-tile |
| manage | 管理入口、统计、操作 | 3 个入口磁贴、刷新、定时任务、设置 | card、manage-entry、manage-actions、stats |
| settings | 本地文件保存目录 | 选择目录、使用默认目录、检查服务；只读输入 | card、settings-actions |
| central-server | 中央服务器、客户端连接 | 启动/关闭/清理端口、启动/关闭客户端、目录选择；URL 输入 | card、service-bar、service-item |
| openai-agent | Agent 服务、单轮对话 | 启动/停止/清理端口、发送；模型选择、文本域 | card、agent-chat-answer |
| local-codex | 任务列表、服务器进程、连接配置、启动提示 | 新增任务、启动/停止、保存、测试连接；URL 输入 | card、review-control |
| local-codex-task | Codex 任务配置、提交 | 添加 Skill、保存设置、提交、取消；路径输入、复选框、文本域 | card、codex-prompt-wrap |
| code-review | 检查配置、实时日志 | 执行/停止、选择目录、添加 Skill、保存、清空；输入、复选框、选择框 | review-header、review-config、review-log-panel |
| test-scheduler | 测试任务、执行记录占位 | 无静态按钮 | card |
| login | 登录表单 | 登录、注册账号；用户名/密码 | auth-card |
| register | 注册表单 | 注册、返回登录；用户名/显示名/密码 | auth-card |
| profile | 账号信息 | 退出登录 | profile-card、profile-details |
| users | 注册用户、现有用户 | 创建用户；文本输入、角色单选 | users-table、role-list |

`index.html` 还提供全局侧边栏导航、折叠按钮和页面返回按钮，它们不属于任一页面片段，但应视作全局组件资产。

## 2. 控件资产分类

### 2.1 按钮

| 类型 | 当前代码表现 | 使用场景 | 建议统一规格 |
| --- | --- | --- | --- |
| 主操作 | `button.primary`，工作台主色背景 | 启动、保存、创建、提交、登录 | 高度 40px；水平 padding 14px；圆角 8px；字重 600 |
| 次操作 | 普通 `button`，白底边框 | 停止、取消、刷新、测试、返回 | 高度 40px；水平 padding 14px；边框 `--color-border-strong` |
| 文字/链接操作 | `.button-link`、`.inline-back`、`#page-back` | 返回、选择目录、低强调入口 | 高度 32~36px；透明背景；保留清晰 focus |
| 紧凑操作 | `.user-save`、review skill 行按钮等 | 表格行内保存、添加/删除 Skill | 高度 32px；水平 padding 10~12px；字号 12~13px |
| 服务危险/停止 | 当前仍多为普通按钮 | 关闭服务、结束任务、清理进程 | 建议增加语义 class（如 `danger`），只统一颜色与禁用态，不改变行为 |
| 图标按钮 | 侧边栏折叠、目录图标 | 无文字或辅助文字按钮 | 必须有 `aria-label/title`；固定 36~40px 方形点击区 |
| 可点击磁贴 | `.module-tile`、`.analysis-task-card` | 模块入口、任务入口 | 保持整块点击；补充键盘 focus/语义 button 或 link |

当前需要重点收敛的差异：`app.css` 的通用按钮约 9/14px、`.button-link` 9/14px、review 局部按钮 8/12px、紧凑按钮 5~7/9~12px；这些应归并到主/次/文字/紧凑四档。

### 2.2 表单控件

- 文本、URL、密码、时间、选择框：统一沿用 40px 高度、9px 12px 内边距、8px 圆角和 `--color-border-strong`。
- 只读路径输入（settings）：允许横向占满剩余空间，保留禁用/只读视觉提示。
- 文本域：建议基础高度 120px；任务输入和分析输入可通过页面修饰类提升到 170/240px，不在 HTML 内写 inline style。
- 复选框、单选框：使用现有浏览器控件即可，统一与 label 的间距为 6~8px；角色组保持 12~14px 间距。
- 所有控件都应保留 `:focus-visible`；现有主色 focus ring 可作为主题换皮入口。

### 2.3 状态与反馈

- 成功：`--color-success-bg` + `--color-success-text`。
- 错误：`--color-danger-bg` + `--color-danger-text`。
- 中性标签：`--color-surface-muted`，圆角胶囊用于状态、分支和短标签。
- 加载中、空数据、失败、禁用、轮询结束应保持独立状态，不通过颜色单独表达；现有分析流程的 `done/active/skipped/failed` 可作为状态组件基线。

## 3. 容器、底板与排版

### 3.1 容器层级

| 层级 | 现有类/区域 | 建议 token |
| --- | --- | --- |
| 页面底色 | `body` | `--color-page-bg` |
| 内容底板 | `.card`、`.review-header`、`.review-config` | 白色/浅色表面，统一 12px 圆角 |
| 强调底板 | `.frontend-hero`、`.package-header`、`.analysis-progress` | 主题渐变或浅色表面，统一 16~18px 圆角 |
| 深色输出底板 | `.review-log-panel`、`.analysis-output` | 深色背景，统一 12~16px 圆角；等宽日志 |
| 入口磁贴 | `.module-tile`、`.analysis-task-card`、`.manage-entry` | 白色表面、边框、卡片阴影、整块 hover |
| 空状态底板 | `.analysis-empty` | 虚线边框、居中、较大垂直留白 |

### 3.2 间距基线

当前 CSS 同时使用 4、6、8、9、10、12、14、16、18、20、22、24、25、28、32、34、36、44、48 等值。建议换皮前先建立 4px 基线，并优先收敛为：

- `space-1 = 4px`：图标与文字、标签内部微间距。
- `space-2 = 8px`：按钮组、表单字段内部、紧凑列表。
- `space-3 = 12px`：字段间、表格行、卡片内小分组。
- `space-4 = 16px`：模块网格、页面分组、普通卡片间距。
- `space-5 = 24px`：卡片 padding、主区域列间距、章节间距。
- `space-6 = 32px`：页面内容横向/纵向留白。
- `space-7 = 48px`：认证页、空状态等大留白。

现有 6/10/14/18/22 等值可在实际改造时分别映射到相邻档位；不要一次性修改所有页面，先改公共 CSS，再逐页回归。

### 3.3 尺寸建议

- 页面主内容：沿用 `#content` 的响应式布局，桌面左右内边距建议统一为 32px，窄屏 20px。
- 普通卡片：padding 24px、圆角 12px。
- 强调卡片：padding 24~32px、圆角 16px。
- 页面标题：一级标题 28px；页面局部标题 18~22px；辅助说明 12~14px。
- 网格列间距统一 16px；复杂分析工作区可使用 24px。
- 服务条目、表格行、表单字段保持 40px 控件高度和 12~16px 行间距。

## 4. 主题换皮接口

当前已有可复用的颜色和阴影变量：`--color-page-bg`、`--color-text`、`--color-text-muted`、`--color-surface`、`--color-surface-muted`、`--color-border`、`--color-border-strong`、`--color-primary`、成功/错误色、`--color-focus`、`--shadow-card`、`--shadow-popover`。后续换皮优先只替换这些 token，并将局部硬编码颜色（如分析页深色输出、前端模块橙色图标、部分渐变）逐步迁入 token。

建议新增但暂不实施的 token 分组：

```css
:root {
  --space-1: 4px; --space-2: 8px; --space-3: 12px;
  --space-4: 16px; --space-5: 24px; --space-6: 32px; --space-7: 48px;
  --control-height: 40px; --control-height-compact: 32px;
  --radius-control: 8px; --radius-card: 12px; --radius-feature: 16px;
  --button-padding-x: 14px; --button-padding-x-compact: 10px;
}
```

## 5. 后续改造顺序

1. 先把 token 和按钮四档落入 `app.css`，保留现有 class 兼容层。
2. 再清理页面内联样式（已知出现在 central-server、openai-agent、server-maintenance）并改为语义 class。
3. 统一可点击磁贴的键盘语义、focus 和禁用态。
4. 按页面族逐组调整：认证页（login/register）、管理与服务页、任务与分析页、配置表单页、占位页。
5. 每组改完做桌面/窄屏截图检查，并核对 HTML 控件、页面 JS selector 和后端路由不变。

## 6. 事实与待确认

- 事实：当前页面由 `app.js` 通过 `/pages/<name>.html` 动态加载；公共样式入口为 `web/assets/css/app.css`。
- 事实：页面专属 JS 已按 `web/assets/js/pages/` 拆分，不能把页面行为复制进 HTML。
- 待确认：是否需要把上述建议直接落地为 CSS 重构；本清单本身不改变页面行为。
- 待确认：主题换皮需要支持几套主题、是否需要运行时切换，以及品牌色/字体/圆角的目标值。

## 附录：页面文件

`central-server.html`、`code-review.html`、`store.html`、`skin-store.html`、`frontend.html`、`local-codex-task.html`、`local-codex.html`、`login.html`、`manage.html`、`openai-agent.html`、`overview.html`、`package-error-analysis-task.html`、`package-error-analysis.html`、`profile.html`、`register.html`、`scheduler.html`、`server-maintenance.html`、`settings.html`、`tasks.html`、`test-scheduler.html`、`users.html`。

