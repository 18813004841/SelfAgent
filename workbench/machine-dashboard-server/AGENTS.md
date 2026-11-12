# 工作台维护专家规则

本文件是 `machine-dashboard-server` 的项目级开发规则。处理本目录内的 Python、HTML、CSS、JavaScript、启动脚本和插件代码时，先阅读本文件以及 [WORKBENCH_DEVELOPMENT_RULES.md](WORKBENCH_DEVELOPMENT_RULES.md)。

## 开发前检查

- 先定位真实入口、路由、配置来源、数据存储和现有实现，再修改代码；不要仅根据页面名称猜测接口或目录。
- 优先复用现有公共模块。新增工具函数前先搜索同类实现，尤其是日志、配置、路径、进程、调度和请求处理。
- 明确区分“当前代码事实”“本次变更”“待确认事项”，不要把推测写成规范或接口契约。

## 日志硬性规则

- Python 业务代码必须使用现有 `core.Log` 提供的 `AppLogger` 或 `core.Log.log_helper` 提供的工厂；禁止在业务模块中直接 `logging.basicConfig`、直接添加 `FileHandler`，或自行创建同类 Logger。
- View 层按功能使用 `get_view_logger()` / `view.logging.get_logger(feature, ...)`；代码检查使用 `get_code_review_logger()`。新增功能先确定功能名和日志目录，再写调用点。
- 运行日志、接口生命周期日志和调试日志按现有配置写入对应目录；禁止把日志写入源码目录、`web/pages` 或临时目录。
- 复用当前启动会话的 `LOCAL_WORKBENCH_START_TIMESTAMP` 文件命名机制，不自行生成另一套时间戳或文件名规则。
- 正常流程用 `info`，可恢复异常用 `warning`，失败和异常用 `error` / `exception`，仅诊断细节用 `debug`。日志消息使用稳定事件名和关键字段，例如 `feature.action.begin`、`feature.action.end`、`feature.action.failed`。
- 日志禁止写入密码、令牌、完整请求凭据和不必要的大段响应；记录对象标识、状态、耗时、数量和错误摘要即可。

## 前后端规则

- 路由、请求参数、返回结构和刷新时机必须与现有 View/Router 实现一致；修改接口时同步检查页面 JavaScript、错误展示和轮询逻辑。
- HTML 负责结构，页面脚本放在 `web/assets/js` 对应功能目录；公共行为放在 `shared`，不要复制粘贴。
- 页面中的“执行日志”应来自后端持久化/接口返回；不能把浏览器 `console.log` 当作业务日志。
- 统一处理加载中、空数据、失败、重复点击和轮询停止条件。

## 验证要求

- Python 修改后至少执行语法编译或项目已有检查；接口修改后检查对应页面调用和错误分支。
- 新增或移动日志目录后确认目录由配置/Logger 创建，并确认 `.gitignore` 不会把源码或配置误加入提交。
- 交付前检查真实文件路径、导入路径、大小写、Markdown 链接和未引用的临时代码。

## 变更记录

新增功能或发现新的稳定约定时，先更新 `WORKBENCH_DEVELOPMENT_RULES.md` 的规则表，再实现代码；规则不明确时记录到“待确认事项”，不要自行扩展约定。
