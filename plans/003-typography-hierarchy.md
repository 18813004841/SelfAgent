# 003 — 统一正文可读性与标题层级

状态：Open  
规则：detector J-4/J-5/J-6（orange）；人工判断 ST-5、KR-7（未绑定验证）。

## 问题

共享 CSS 在 `.collapse` 使用 `line-height: 1`；多个状态和辅助文本为 12–13px。多个页面从 `h1` 直接跳到 `h3`，例如 `users.html`、`settings.html`、`scheduler.html`、`local-codex.html`、`central-server.html`、`openai-agent.html`，破坏文档层级。

## 目标

正文和状态信息采用可读的共享类型角色：正文至少 14px、line-height 1.5；仅真正的 metadata/表头可保留较小字号，并提高其语义对比度。每个页面保持一个 h1，页面区块按 h2，区块内子区按 h3；不改变现有内容顺序。

## 步骤

1. 为正文、辅助文本、表头建立 CSS 类型角色，替换 `.collapse` 的 `line-height: 1` 和 detector 命中的 12/13px 声明。
2. 在所有命中页面把直接从 h1 到 h3 的区块标题改为 h2；现有 h3 子区块在其父 h2 下保留。
3. 检查动态插入标题（尤其任务、用户和调度列表）是否沿用同一层级。
4. 不把中文文案改成英文占位词；保留现有业务命名。

## 范围边界

不改变页面信息架构、接口返回、表格列、状态文案或响应式布局。

## 验证

- 对每个页面用 DOM outline 检查 h1→h2→h3 无跳级。
- 在 100% 与移动宽度检查正文、状态、表头的可读性和换行。
- 检查 `schedule-status`、`review-result`、`review-success` 的语义颜色仍区分成功、失败和运行中。
