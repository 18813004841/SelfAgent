# 工作台开发规范

## 功能概述

本规范服务于 `machine-dashboard-server` 工具台，覆盖 Python 服务、调度器、进程管理、HTML 页面、JavaScript 页面逻辑、插件和启动脚本。目标是让新增功能优先复用现有基础设施，并让问题可以通过功能日志快速定位。

## 项目模块

- `src/`：Python 服务、路由、配置、存储、调度和功能模块
- `web/`：HTML、CSS、JavaScript 和页面静态资源
- `launchers/`：外部进程或客户端启动器
- `plugins/`：可选扩展
- `skills/`：工作台内置工作流技能；加载和分发方式待接入时确定
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

同一启动会话和日志文件由 `AppLogger` 共享一个轮转 Handler，避免多个功能 Logger
同时轮转同一文件造成 Windows 文件锁冲突；新增日志功能必须继续使用现有工厂。

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

- 代码检查达到失败阈值的问题可通过飞书自定义机器人发送群通知；消息显示当前任务列表中的名称。Webhook 保存在服务端用户级配置目录，代码检查授权页面可读取、更新或清除，环境变量作为后备。使用 Git blame 邮箱经已授权的 lark-cli 查找人员，查询或发送失败写入报告警告，不改变检查结论或成功基线。
- 代码检查的问题报告和飞书通知仅包含成功基线与当前快照之间新增或修改的 C# 代码行；合并后体现在该差异中的代码同样检查，旧行仅供上下文使用。

- 中央客户端启动时由已登录页面读取服务端提供的连接信息并传给 Local Agent；客户机不持久化中央服务器地址。跨机器地址可由 MACHINE_CONTROL_PUBLIC_URL 指定，未指定时使用工作台访问主机名和中央服务端口。
- 认证与模块权限统一在服务端 HTTP 入口校验；用户、权限和会话数据沿用 `core.storage` 的用户级 SQLite，页面隐藏不能替代 API 鉴权。

- Python 导入使用现有包结构，避免通过修改 `sys.path` 绕过真实依赖。
- 配置、用户数据、输出物和日志路径集中由 `core.settings` 或现有存储模块管理。
- 业务模块不要自行初始化全局日志、数据库连接或重复的路径解析。
- JavaScript 公共逻辑放入 `web/assets/js/shared`，页面专属逻辑放入 `pages`；轮询必须有变化检测和停止条件。
- 通用短提示通过 `shared/tips.js` 展示，默认两秒消失；37工程参数共享保存在工作台服务端 SQLite，连接同一服务端的客户端和授权账号读取同一份参数，页面打开时回填；共享配置尚未保存时可读取当前账号的历史配置。
- HTML 页面沿用现有公共样式、导航和错误提示模式，新增按钮必须处理禁用和重复点击。

- Jenkins 管理配置保存在工作台用户级 SQLite；在线状态由服务端探测，中央连接状态复用控制中心 Worker 心跳。

- KOA 单任务构建查询沿用工作台登录与 manage 权限，只允许访问已登记的 Jenkins，以匿名 GET 读取最后完成构建；不转发用户会话或管理凭据，也不轮询。

- Jenkins 用户注册对所有已登录的工作台用户开放；注册密码仅用于当前请求，不记录或持久化。Jenkins 地址管理仍需 manage 模块权限。

- Jenkins 权限管理仅允许工作台管理员；凭据从服务器用户级 server-settings.json 的 jenkins_management 或服务进程环境读取，权限写入支持方案或明确的逐项选择，须检测授权配置并发变化、校验目标实例的可用项并保留其他主体。每台 Jenkins 的 qa、admin 方案存储于工作台用户级 SQLite，角色授权以全局与项目角色为单位分配；旧版名称可能同时代表用户和组，页面须明确提示，非 Jenkins 内置用户库不允许通过此入口保存角色。

- 机器管理助手每次启动 Codex CLI 时，仅对 machine_control MCP 服务配置工具自动批准；其他工具沿用原有审批设置。
- 打包分析使用仅暴露预绑定日志读取工具的 machine_control MCP 会话，由 Codex 提交任务；工作台校验任务目标后从中央服务器读取原始日志，失败不静默切换其他执行方式。
- 机器管理助手在浏览器会话中保存 Codex 返回的会话 ID，后续消息使用该 ID 恢复上下文；旧会话没有 ID 时从下一条消息开始建立新的 Codex 会话。
- 机器管理助手使用独立的流式接口逐条展示 Codex 事件，原同步接口保持兼容；服务端检测到连接中断后停止对应的 Codex 执行。
- 机器管理助手在服务进程内阻止同一 Codex 会话并发执行；其他进程占用会话时提示等待，不自动新建会话或重试操作。
- 机器管理助手允许 Codex 最多运行 15 分钟，以覆盖较长的机器控制任务；超时或取消时清理本地 Codex 进程树，不假定远程任务已停止。

- 服务器开发维护入口使用模块卡片；37工程维护继承服务器开发维护模块权限；预检只读取本机 Git 仓库和远端引用；执行使用服务端本机工作区，按 reset --hard、clean -fd、checkout -- . 清理每个仓库的已跟踪修改和非忽略的未跟踪文件，再重置目标分支到 origin，默认仅提交本地更改；任务成功后可由用户单独触发非强制推送。合并冲突在 Game/BuildFolder 外保留新分支（tag）侧，Game/BuildFolder 冲突暂停等待管理员处理。操作前检查两个仓库实际 Git 索引锁（包括 worktree），锁存在时停止且不自动删除；Git 错误显示仓库、操作和安全的原因摘要，不暴露凭据；大仓库的切分支和合并操作允许最多一小时，超时后仅在核验合并提交、分支和工作区后继续。Unity 编辑器路径保存在共享的 37 工程参数中，未指定时沿用环境变量或 Hub 路径；版本维护在创建新分支后启动独占的 Unity batch mode，会话暂停自动刷新和程序集重载直到导表完成，随后恢复并检查脚本编译；冲突暂停期间保持同一 Unity 会话。原服务器 Codex 维护及重启接口已移除，历史会话数据不主动删除。

- 37 工程编译成功后，工作流等待本次启动的 Unity 正常退出；超时则强制结束该进程并核验退出，成功时在任务日志提示，失败时任务报错。
- 37 工程导表提交包含正式输出的 ConfigGen、ConfigGenFB 目录，以及 FlatBuffers_Gen_CS_Temp 下同名的两个生成代码目录。
- 37 工程 Unity 会话就绪并暂停自动刷新和程序集重载后，合并前再次清理工程工作区；清理未跟踪文件时保留当前任务的临时会话桥接文件及其 meta，不触发 Unity 刷新或编译。
- 37 工程推送仅发送任务成功时记录的提交；工作区和暂存区的未提交改动不阻止推送，也不会包含在推送中。仍须核对当前分支、提交和远端分支状态。
- Unity 编辑器可指定 Windows 可执行文件、macOS Unity.app 或其内部可执行文件；未指定时按服务端系统查找 Unity Hub 默认路径。

## 待确认事项

- 是否需要为每个功能统一增加独立的 `logs/<feature>/` 目录，还是继续由现有 View/操作日志工厂决定目录。
- 是否建立统一的前端请求封装，以统一超时、错误消息和请求级追踪字段。
- 是否将当前历史模块中的直接 `logging` 调用分批迁移到公共 Logger；迁移前需确认兼容范围和日志检索需求。

## 变更记录

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-11-25 | 打包报错分析使用 LangGraph 编排归档优先及 Worker 回退，任务状态仍保存在工作台 SQLite | `src/package_error_analysis/pipeline.py` |
| 2026-11-25 | 预留工作台内置工作流技能目录，与仓库开发流程技能及用户运行数据区分 | `skills/README.md` |
| 2026-11-21 | Jenkins 注册页面与注册接口对已登录用户开放；Jenkins 地址管理沿用管理模块权限，权限管理仅管理员可用 | `src/core/permissions.py`、`web/pages/jenkins.html` |
| 2026-11-12 | 建立工作台项目级维护规则，明确 Logger 复用、按功能分区、前后端联动和验证要求 | `src/core/Log/logger.py`、`src/core/Log/log_helper.py`、`src/view/logging.py`、`src/core/settings.py` 当前实现 |

- View 日志路径统一由 `core.settings.Settings.output_dir` 决定；View 模块传入的历史目录参数不再决定实际写入位置。
