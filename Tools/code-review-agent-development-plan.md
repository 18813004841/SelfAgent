# 本地增量代码检查 Agent 开发计划

## 1. 功能概述

系统配置目标工程目录和检查分支，在每次检查时获取该分支自上次检查以来的提交增量，执行本地代码规范检查、测试和工程内 Skill 规则检查，再按需调用 Agent 进行语义审查，生成可追踪的检查报告。

核心原则：本地 Git 获取增量；commit SHA 管理检查基线；确定性工具优先；Agent 只负责语义审查；普通聊天和代码审查分开；检查任务异步执行。

实现入口：[Tools/code-review-agent](./code-review-agent/README.md)。当前已完成目录骨架、配置模型、Git 增量、规则发现、Unity Runtime 边界检查、本地模型客户端、流水线、CLI、README 和架构流程图；后续按阶段补充真实 Unity 编译命令、异步任务和 Web 展示。

## 2. 第一版范围

### 2.1 包含

- 配置多个目标工程、目录、分支和检查命令。
- fetch、checkout、pull 和 commit SHA 基线管理。
- 生成提交、文件和行级增量。
- 自动发现 AGENTS.md、README.md、skills/**/SKILL.md 等规则。
- 执行 lint、类型检查、测试和安全扫描。
- 对变更文件分批调用 Agent。
- 生成 JSON 和 Markdown 报告。
- 展示检查进度、耗时、模型调用次数和错误。

### 2.2 不包含

- 自动修改代码并提交、自动合并分支。
- 依赖 ChatGPT 桌面端 UI 自动操作。
- 全仓库模型审查。
- GitHub PR 评论和状态回写。
- 第一版向量数据库和复杂代码知识图谱。

## 3. 总体架构

~~~text
Web/API 或本地调度器
        │
        ▼
Check Service
        │
        ├── Project Config
        ├── Git Manager
        ├── Baseline Store
        ├── Diff Collector
        ├── Skill/Rule Loader
        ├── Deterministic Check Runner
        ├── Context Builder
        ├── Agent Reviewer
        ├── Report Aggregator
        └── Progress/Log Store
        │
        ▼
SQLite + Markdown/JSON Reports
~~~

| 模块 | 职责 |
|---|---|
| Project Config | 保存目标工程、分支、同步策略和检查命令 |
| Git Manager | fetch、checkout、pull、获取 SHA、检测工作区 |
| Baseline Store | 保存上次检查 SHA、状态和时间 |
| Diff Collector | 生成变更文件、diff、行和提交摘要 |
| Skill Loader | 发现并解析工程规则和 Skill |
| Check Runner | 调用 lint、类型检查、测试和安全工具 |
| Context Builder | 构造最小模型上下文 |
| Agent Reviewer | 批量调用模型进行语义审查 |
| Report Aggregator | 合并工具结果和模型结果 |
| Progress Store | 保存阶段状态、日志和耗时 |

## 4. 增量获取和基线

### 4.1 Git 流程

1. 检查目标目录是否为 Git 仓库。
2. 检查工作区是否允许同步。
3. fetch 目标远端分支。
4. checkout 目标分支。
5. 使用 fast-forward 方式更新。
6. 获取当前 HEAD SHA。
7. 读取上次检查基线。
8. 执行 old_sha..current_sha 的 diff。

~~~powershell
git fetch origin <branch>
git checkout <branch>
git pull --ff-only origin <branch>
git rev-parse HEAD
git diff --name-status <old_sha> <current_sha>
git diff --unified=20 <old_sha> <current_sha>
~~~

### 4.2 基线数据

~~~json
{
  "project_id": "self-agent",
  "branch": "main",
  "last_attempted_sha": "abc123",
  "last_successful_sha": "abc123",
  "current_sha": "def456",
  "status": "passed"
}
~~~

### 4.3 基线更新规则

| 检查结果 | 处理 |
|---|---|
| passed | 更新成功 SHA 和尝试 SHA |
| failed | 更新尝试 SHA，保留成功 SHA |
| error | 不更新成功基线 |
| 无新提交 | 不调用模型，返回 skipped |

## 5. 检查流水线

### 5.1 快速路径

~~~text
读取配置 → 获取 Git 增量 → 发现规则和 Skill → 执行本地 lint/type/test → 汇总确定性结果
~~~

格式、语法类问题优先由本地工具报告；业务逻辑、接口、权限、数据库和并发问题才调用 Agent。

### 5.2 Agent 路径

~~~text
筛选变更文件 → 按文件或模块分批 → 提取变更函数和必要上下文 → 加载匹配 Skill → 附加工具结果 → 调用模型 → 校验 JSON → 汇总
~~~

Agent 不接收整个工程。每批包含文件路径、unified diff、变更函数或类、必要上下文、匹配规则和本地工具结果。

### 5.3 限制

| 限制项 | 建议值 |
|---|---:|
| 单文件模型输入 | 不超过 8,000 tokens |
| 单次模型请求 | 不超过 20,000 tokens |
| 单次模型调用次数 | 5 次 |
| 单次检查时长 | 120 秒 |
| 单批文件数 | 10 个 |
| 单提交文件数 | 50 个 |

超过限制时输出“检查不完整”并列出未检查文件。

## 6. Skill 和规则发现

默认扫描：

~~~text
<project>/AGENTS.md
<project>/README.md
<project>/CONTRIBUTING.md
<project>/.codex/
<project>/.github/
<project>/skills/**/SKILL.md
<project>/.skills/**/SKILL.md
~~~

第一版采用规则匹配：按扩展名、目录前缀、Skill 适用范围和 API/数据库/UI/测试关键字匹配，不引入向量检索。

Skill 建议格式：

~~~markdown
# Python API Skill

## 适用范围
src/api/**/*.py

## 检查要求
- 所有请求参数必须校验
- 新增接口必须补充测试
- 错误响应使用统一结构

## 检查命令
ruff check src/api
pytest tests/api
~~~

报告必须标明匹配到的 Skill、已执行命令、未执行要求和违反规则。

## 7. 确定性检查工具

工具由项目配置定义：

~~~yaml
checks:
  - name: ruff
    command: "ruff check src"
    timeout_seconds: 120
  - name: pytest
    command: "pytest tests"
    timeout_seconds: 300
~~~

Unity C# 第一版建议支持：

- `dotnet format --verify-no-changes`：仅在工程生成了可用的 .NET solution 时启用；
- Roslyn 分析器或 Unity 工程已有的代码分析命令；
- Unity Editor batchmode 编译检查：由项目配置提供 Unity 可执行文件和检查脚本；
- Unity EditMode/PlayMode 测试：由项目配置提供测试命令；
- `semgrep` 或其他安全扫描：仅在规则适用于 C# 时启用。

不默认直接执行 `dotnet build` 或 `dotnet test`，因为 Unity 工程的真实编译和测试环境通常由 Unity Editor、Packages 和项目设置决定。具体命令必须通过项目配置提供。

统一结果格式：

~~~json
{
  "check_name": "ruff",
  "status": "failed",
  "file": "src/api/user.py",
  "line": 28,
  "severity": "error",
  "message": "unused import",
  "duration_ms": 1200
}
~~~

## 8. Agent 设计

### 8.1 模型服务实现方式

本项目的模型调用层仿照 `workbench/machine-dashboard-server/launchers/openai_agent/` 的分层方式实现，但作为代码检查模块自己的独立客户端，不导入、不复用 `AiAgent/AiProject/Codes/Agents/OpenAiAgent/` 的代码。

建议在代码检查模块内提供独立的 `model_service/client.py`、`config.py`、`protocol.py` 和 `errors.py`。客户端负责本地模型服务器的 HTTP 请求、超时、响应解析和错误转换；代码检查流水线只依赖抽象的 `chat()`/`stream()` 接口。

已确认的本地模型服务协议如下：

| 项目 | 已确认值 |
|---|---|
| 基础地址 | `http://127.0.0.1:8765/v1` |
| 请求接口 | `POST /v1/chat/completions` |
| API Key | 不需要 |
| 流式响应 | 支持 `stream=true` |
| 返回结构 | 第一版由代码检查客户端约定为结构化 JSON |

流式协议采用标准 SSE，由本地模型服务和客户端共同遵守。第一版约定：每个事件使用 `data: <json>\\n\\n`，增量文本放在 `choices[0].delta.content`，正常结束发送 `data: [DONE]`。`[DONE]` 是本项目协议约定，不是模型天然决定的内容；如果本地服务器自行实现接口，就由服务器按此规则输出。

第一版不把思考内容发送到报告，不要求模型返回内部推理过程；如果服务返回 reasoning 字段，客户端只记录长度和耗时，不保存其正文。第一版不启用模型工具调用，工具由代码检查服务在模型调用前后显式执行。遇到未知事件类型时忽略并记录日志，不能导致整次检查失败。

模型名称固定默认使用 `gpt-5.6-sol`，仍允许项目配置覆盖。

该地址使用 `8765` 端口，需要确认它不会和现有 `OpenAiAgent` 网关同时监听同一个端口。代码检查服务只把它作为外部模型 HTTP 服务使用，不启动或管理该模型服务进程。

模型服务接口为：

~~~text
POST <LOCAL_MODEL_API_URL>/chat/completions
GET  <LOCAL_MODEL_API_URL>/models 或 <LOCAL_MODEL_HEALTH_URL>
~~~

请求至少包含 `model`、`messages` 和 `stream`。协议若不是 OpenAI 兼容格式，只修改 `model_service/client.py` 和 `protocol.py`，Git、Skill、检查流水线和 Agent 审查逻辑不感知具体模型服务。

客户端必须支持：

- 单次非流式请求，供结构化代码审查使用；
- 可选流式请求，供页面实时显示进度；
- 连接超时、读取超时和最大响应大小；
- 模型服务不可用时返回明确错误，不阻塞本地 lint/test 结果；
- 记录请求开始、首 token、完整响应、模型名和耗时；
- 不在代码中写死 Token，使用环境变量或本地配置；
- 对返回 JSON 做 schema 校验，非法结果允许一次重试或降级为文本结果。

### 8.1.1 超时方案

单次请求采用分阶段超时，不能只设置一个无限等待的总超时：

| 超时项 | 默认值 | 作用 |
|---|---:|---|
| 连接超时 | 3 秒 | 本地服务未启动或端口不可用时快速失败 |
| 首 token 超时 | 30 秒 | 服务已连接但模型迟迟没有开始输出时失败 |
| 读取间隔超时 | 30 秒 | 流式输出中长时间没有新内容时失败 |
| 总请求超时 | 120 秒 | 限制一次代码审查请求的最长时间 |

普通问答可以使用 60 秒总超时，代码审查使用 120 秒；跨文件审查或本地模型首次加载时允许通过项目配置提高到 180 秒。超时后保留本地 lint/test 结果，并将 Agent 状态标记为 `timeout`，不更新成功基线。

### 8.1.2 上下文长度方案

客户端通过 `/v1/models` 查询本地模型的真实上下文窗口和最大输出能力，不能直接把 ChatGPT 应用界面的限制写死到服务中。不同模型、接口和部署版本可能有不同上限，因此采用“模型能力上限 + 客户端安全上限 + 代码审查批次上限”三层限制：

1. 从 `/v1/models` 读取当前模型的上下文窗口和最大输出；读取不到时使用保守默认值。
2. 单次请求保留输入、输出和安全余量，不能把窗口全部用于输入。
3. 代码审查按文件或模块拆分，不发送整个仓库。

第一版默认值（服务未返回能力信息时使用）：

| 项目 | 默认值 |
|---|---:|
| 假定模型上下文窗口 | 32,000 tokens |
| 单次输入安全上限 | 12,000 tokens |
| 单次输出上限 | 2,000 tokens |
| 系统提示、规则和 Skill 预算 | 2,000 tokens |
| 安全余量 | 4,000 tokens |
| 单文件 diff 建议上限 | 6,000 tokens |

计算原则：`输入上限 + 输出上限 + 系统/规则预算 + 安全余量 <= 模型上下文窗口`。如果 `/v1/models` 返回 16,000 tokens，客户端应自动把单次输入上限降到 6,000～8,000 tokens，并增加分批次数；即使服务返回更大的窗口，也必须保留输出和安全余量。

如果一个文件超过单文件上限，按变更函数或代码块拆分；如果一个提交超过批次上限，按模块并行审查，再进行一次只包含摘要的跨文件汇总。长度估算优先使用 tokenizer，暂时没有对应 tokenizer 时使用字符数估算并保留 20% 余量。

### 8.1.3 首次检查基线

没有历史 SHA 时，第一版默认基线时间点为“检查时间往前 7 天，当天凌晨 04:00（Asia/Shanghai）”。系统选择该时间点之前的目标分支最后一条提交作为初始 SHA：

~~~text
baseline_time = local_check_time - 7 days
baseline_time = date(baseline_time) 04:00:00 Asia/Shanghai
initial_sha = last_commit_before(baseline_time)
~~

首次检查范围为 `initial_sha..current_sha`。如果找不到该时间点之前的提交，则使用仓库最早提交，并在报告中标记 `initial_baseline_fallback=true`。

### 8.1.4 模型不可用策略

模型服务连接失败、超时、返回非法结构或健康检查失败时，不允许检查通过。确定性工具结果仍然保存，但任务最终状态为 `error` 或 `agent_unavailable`，成功基线不更新。

建议配置：

~~~yaml
model_service:
  api_url: "http://127.0.0.1:8765/v1"
  model: "gpt-5.6-sol"
  connect_timeout_seconds: 3
  first_token_timeout_seconds: 30
  read_idle_timeout_seconds: 30
  timeout_seconds: 120
  context_window_tokens: 32000
  max_input_tokens: 12000
  max_output_tokens: 2000
  stream: false
  enabled: true
~~~

该客户端只作为代码检查服务的依赖，不注册为 `OpenAIAgentLauncher`，不启动或停止 `OpenAiAgent`，也不读取其 OAuth、网关或 Agent 实现。

Agent 只允许使用受限工具：

~~~text
get_diff()
read_file(path, start_line, end_line)
read_symbol(file, symbol)
find_definition(symbol)
find_references(symbol)
list_project_rules()
list_matching_skills()
get_check_results()
~~~

所有路径必须限制在目标工程目录内，模型输出不能直接执行任意命令。

输出必须是结构化 JSON，包含 passed、findings、reviewed_files 和 unreviewed_files。独立文件并行审查；高风险文件使用高质量模型；以 commit_sha、file_hash、rule_version、model_version 做缓存；模型不可用时保留本地检查结果。

## 9. 性能和交互

必须记录：

~~~text
prepare_ms, git_ms, skill_load_ms, deterministic_checks_ms,
model_queue_ms, model_first_token_ms, model_generation_ms,
report_ms, total_ms
~~~

建议目标：

| 场景 | 目标 |
|---|---:|
| 无新提交判断 | 小于 2 秒 |
| Git 增量获取 | 小于 10 秒 |
| 本地静态检查 | 小于 60 秒 |
| 普通小提交完整检查 | 小于 120 秒 |
| 页面首个进度 | 小于 1 秒 |

检查必须异步化：

~~~text
POST /checks → 返回 run_id
GET /checks/{run_id} → 返回阶段和进度
GET /checks/{run_id}/report → 返回最终报告
~~~

普通聊天接口不得默认触发代码读取、Git 操作或多轮 Agent。

## 10. 数据模型

### projects

id、name、path、remote、branch、auto_fetch、enabled。

### check_runs

id、project_id、old_sha、current_sha、status、phase、started_at、finished_at、duration_ms、model_calls。

### findings

id、run_id、source、file、line、severity、rule、message、suggestion、confidence。

## 11. 开发阶段计划

### 阶段 0：现状验证

确认 Python、依赖、服务启动方式、目标工程 fetch 权限、模型 SDK、认证和流式接口；记录简单请求的首 token 和完整响应耗时。

产出：运行环境记录、模型耗时基线和样例配置。

### 阶段 1：Git 增量和基线

实现项目配置、Git Manager、SQLite 基线、diff 文件列表和提交摘要；处理无新提交、分支不存在、工作区冲突和 fetch 失败。

验收：正确得到 old_sha..current_sha，失败时不错误更新成功基线。

### 阶段 2：Skill 和本地检查

扫描 AGENTS.md 和 SKILL.md；实现适用范围匹配、可配置检查命令、统一输出解析、日志和耗时保存。

验收：能匹配 Skill，能追溯 lint/test 结果，工具超时不会卡死。

### 阶段 3：异步任务和进度

创建检查任务和后台执行器；增加阶段状态、进度接口、重试和页面展示。

验收：创建接口快速返回 run_id，异常任务可查询。

### 阶段 4：Agent 语义审查

实现变更函数提取、分批上下文构建、流式调用、并行审查、调用上限、缓存、JSON 校验和结果聚合。

验收：不发送整个仓库，能定位文件和行号，模型失败时仍有本地报告。

### 阶段 5：报告和治理

实现 Markdown/Web 报告、严重级别、通过策略、历史记录、规则版本、模型版本和可选通知。

## 12. 安全要求

- 只允许访问配置的工程目录；
- 禁止自动执行破坏性 Git 命令；
- 工作区有未提交修改时默认停止同步；
- pull 使用 --ff-only；
- 检查命令使用白名单或配置审批；
- 进程设置超时和输出大小限制；
- 日志隐藏 Token、密码和私钥；
- 默认不向外部模型发送代码，项目级配置显式开启；
- 发送前扫描 API Key、Token、密码、私钥和数据库连接串。

## 13. 首个实现切片

~~~text
配置一个本地工程
→ 指定一个分支
→ 获取 old_sha..current_sha
→ 输出变更文件和 diff
→ 扫描 SKILL.md
→ 执行一个 lint 命令
→ 保存一次 check_run
→ 生成 Markdown 报告
~~~

完成这个闭环后再接入模型，先验证 Git、基线、权限和报告结构。

## 14. 待确认事项

| 问题 | 当前建议 |
|---|---|
| 模型服务 | 已确认使用 `http://127.0.0.1:8765/v1`，兼容 `/chat/completions`，支持流式，无 API Key |
| 8765 端口 | 已确认由本地模型服务独占 |
| 模型名称 | 已确认使用 `gpt-5.6-sol` |
| 目标工程类型 | 已确认第一版支持 Unity C# 工程 |
| 任务执行方式 | 复用现有本地调度器，不足时增加 worker |
| 报告存储 | SQLite + Markdown/JSON |
| GitHub API | 第一版不需要，后续用于 PR 状态和评论 |
| 自动修复 | 第一版不做 |
| 代码外发 | 项目级配置决定，默认关闭 |
| Web 页面 | 复用现有工作台页面，入口待确认 |
| 通过阈值 | `critical/high` 失败，`medium` 警告，`low/info` 提示 |
| 模型返回结构 | 第一版统一为结构化 JSON，后续按实际模型输出优化 |
| 模型真实上下文窗口 | 第一版不依赖 `/v1/models`；按 32,000 tokens、12,000 输入和 2,000 输出的客户端限制实施，后续可优化 |
| SSE 结束标记 | 已约定使用 `data: [DONE]` |
| 思考内容 | 第一版不写入报告；仅记录是否出现及耗时 |
| 工具调用 | 第一版不启用模型工具调用，由检查服务显式执行工具 |
| 首次基线 | 已约定使用检查时间往前 7 天对应日期 04:00（Asia/Shanghai）前最后一条提交 |
| 模型不可用 | 不允许通过；任务标记失败或不可用，成功基线不更新 |
| Unity 检查环境 | 第一版只检查编译问题、Runtime 引用 Editor 代码/命名空间，其余遵循工程 Skill；具体命令后续按目标工程补充 |

