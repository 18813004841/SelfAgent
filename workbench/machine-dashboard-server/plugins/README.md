# 工具注册规范

工具由 `tool_id + args` 调用。工具记录保存入口、工作目录、类型和启用状态；任务只引用 `tool_id`，不保存任意完整 shell 命令。

当前支持类型：`local_process`。

本地进程入口需支持：

```text
python entry.py --input '{"key":"value"}'
```

成功退出码为 0，标准输出作为执行结果。
