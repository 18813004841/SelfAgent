# 工作台开发规范

## 功能概述

本规范服务于 `machine-dashboard-server` 工具台，覆盖 Python 服务、调度器、进程管理、HTML 页面、JavaScript 页面逻辑、插件和启动脚本。目标是让新增功能优先复用现有基础设施，并让问题可以通过功能日志快速定位。

## 项目模块

- `src/`：Python 服务、路由、配置、存储、调度和功能模块
- `web/`：HTML、CSS、JavaScript 和页面静态资源
- `launchers/`：外部进程或客户端启动器
- `plugins/`：可选扩展
- `logs/`：运行产物目录，不提交日志内容
- [项目执行规则](AGENTS.md)：供维护助手和后续开发直接遵循

## 当前日志实现

### 已确认的公共入口

| 场景 | 入口 | 现状 |
| --- | --- | --- |
| 通用应用日志 | `src/core/Log.AppLogger`、`core.Log.log_helper.get_default_logger` | 读取 `core.settings` 的等级、调试开关和日志根目录 |
| View 接口日志 | `core.Log.log_helper.get_view_logger` 或 `src/view/logging.py` 的 `get_logger` | 区分接口生命周期与功能调试日志 |
| 代码检查 | `core.Log.log_helper.get_code_review_logger` | 写入代码检查功能目录 |
| 进程/操作日志 | `process_manager.operation_log.get_operation_logger` | 供启动器、调度和操作流程复用 |

### 日志路径与启动约定

- `core.settings.get_settings()` 是日志路径和等级的配置来源。
- 默认用户数据根目录由平台决定；日志根目录位于用户配置目录的 `logs` 下，View 日志位于其 `view` 子目录。
- 工作台启动时由 `src/server.py` 初始化 `LOCAL_WORKBENCH_START_TIMESTAMP`；`AppLogger` 要求该值存在，并以同一启动会话的时间戳文件追加写入。
- 功能日志可以使用相对功能目录，由 `AppLogger` 相对日志根目录解析；不要把相对路径解释为源码目录路径。

### 推荐调用

```python
from core.Log.log_helper import get_view_logger

logger = get_view_logger("calendar")
logger.info("calendar.event.create.begin user_id=%s", user_id)
try:
    result = create_event(payload)
except Exception:
    logger.exception("calendar.event.create.failed")
    raise
```

## 功能开发流程

1. 搜索已有入口和公共实现，确认功能归属、数据流和日志目录。
2. 先定义接口契约：方法、路径、参数、返回值、错误分支和刷新时机。
3. 实现后端功能与日志，再接入页面；每个关键动作至少有开始、结束或失败信息。
4. 处理空数据、加载中、重复触发、超时和异常展示。
5. 执行语法/静态检查，检查页面调用、日志路径和版本控制状态。
6. 将新发现的稳定约定补充到本文件，将不确定内容放入待确认事项。

## 代码约定

- Python 导入使用现有包结构，避免通过修改 `sys.path` 绕过真实依赖。
- 配置、用户数据、输出物和日志路径集中由 `core.settings` 或现有存储模块管理。
- 业务模块不要自行初始化全局日志、数据库连接或重复的路径解析。
- JavaScript 公共逻辑放入 `web/assets/js/shared`，页面专属逻辑放入 `pages`；轮询必须有变化检测和停止条件。
- HTML 页面沿用现有公共样式、导航和错误提示模式，新增按钮必须处理禁用和重复点击。

## 待确认事项

- 是否需要为每个功能统一增加独立的 `logs/<feature>/` 目录，还是继续由现有 View/操作日志工厂决定目录。
- 是否建立统一的前端请求封装，以统一超时、错误消息和请求级追踪字段。
- 是否将当前历史模块中的直接 `logging` 调用分批迁移到公共 Logger；迁移前需确认兼容范围和日志检索需求。

## 变更记录

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-11-12 | 建立工作台项目级维护规则，明确 Logger 复用、按功能分区、前后端联动和验证要求 | `src/core/Log/logger.py`、`src/core/Log/log_helper.py`、`src/view/logging.py`、`src/core/settings.py` 当前实现 |
