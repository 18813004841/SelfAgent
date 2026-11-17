# 工作台定时任务模型

## 任务字段

| 字段 | 说明 |
|---|---|
| id | 稳定任务 ID |
| name | 任务名称 |
| task_type | `scheduled` 定时任务、`invoke` 调用任务、`cancel` 取消操作记录 |
| schedule_type | `interval` 或 `once` |
| schedule_expr | 调度表达式或间隔秒数 |
| dispatcher | 执行调度器名称，默认 `scheduler` |
| last_status | `queued/running/cancelling/succeeded/failed/cancelled` |
| progress_current | 当前进度 |
| progress_total | 总进度 |
| tool_id | 要调用的工具 |
| args | 工具参数，包括工程路径、分支和 Skill 配置 |

列表页展示任务摘要，点击后请求 `/api/schedules/{id}` 展示完整配置和最近 30 次运行记录。取消操作只写入 `cancel_requested`，执行器在安全边界更新为 `cancelled`，不会强制杀死不受控的子进程。

代码检查工具建议使用 `local_process` 注册，参数包含：

~~~json
{
  "project_path": "E:/Projects/MyUnity",
  "branch": "main",
  "skill_paths": ["skills"],
  "config_path": "config.json"
}
~~~
