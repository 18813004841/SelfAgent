# ADR-001：工作台持久化 Repository 边界

- 状态：已采用（2026-11-16）
- 范围：`workbench/machine-dashboard-server`

## 决策

Local Codex 任务的 SQL 集中在 `src/core/repositories.py` 的
`LocalCodexTaskRepository`。View 只负责参数校验、响应和调用任务执行器；Repository
负责短连接、事务提交和字段白名单。数据库基础设施仍由 `core.storage.connect` 管理。

后台 `src/local_codex/tasks.py` 的任务完成回调同样使用该 Repository，避免后台执行路径重复创建连接和散落 SQL。

## 原因与兼容性

保留现有 HTTP 路由、JSON 字段和 SQLite 表，因此页面和旧数据库无需迁移。该变更是
渐进式边界迁移；调度、工具和运行记录中的旧 SQL 仍列为技术债，后续按调用频率迁移。

## 回滚

恢复 `local_codex_view.py` 原有 SQL 调用即可；本次没有修改表结构或删除数据。

