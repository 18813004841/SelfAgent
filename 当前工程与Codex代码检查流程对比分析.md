# 当前工程与 Codex 代码检查流程对比分析

## 1. 分析范围和依据

本分析基于当前工作区中的代码检查实现：

- workbench/machine-dashboard-server/tools/code-review-agent/code_review/pipeline.py
- workbench/machine-dashboard-server/tools/code-review-agent/code_review/git.py
- workbench/machine-dashboard-server/tools/code-review-agent/code_review/checks.py
- workbench/machine-dashboard-server/tools/code-review-agent/code_review/model_service.py
- workbench/machine-dashboard-server/tools/code-review-agent/code_review/cli.py
- workbench/machine-dashboard-server/tools/code-review-agent/README.md
- workbench/machine-dashboard-server/tools/code-review-agent/docs/architecture.md
- workbench/machine-dashboard-server/src/schedulers/code_review_scheduler.py
- 线程记录：codex检查过程记录.md

其中，“Codex 流程”指线程 01a1d3cf-8082-7531-a128-b2bb7e51068c 中已经实际执行的两轮检查。

## 2. 两套流程并列图

~~~mermaid
flowchart LR
  subgraph ENGINE["当前工程：自动化代码检查工作流"]
    E1[接收工程路径与分支] --> E2[加载配置]
    E2 --> E3[checkout / fetch / pull]
    E3 --> E4[读取 last_successful_sha]
    E4 --> E5{是否有新提交}
    E5 -->|否| E6[生成 skipped 报告]
    E5 -->|是| E7[读取 Git diff]
    E7 --> E8[只保留 Game/Assets/*.cs]
    E8 --> E9[编码与变更文件校验]
    E9 --> E10[Runtime Editor 边界检查]
    E10 --> E11[本地确定性检查器]
    E11 --> E12[加载匹配的 AGENTS/SKILL]
    E12 --> E13[生成规则与工具匹配计划]
    E13 --> E14[执行编译命令]
    E14 --> E15[按规则筛选模型范围]
    E15 --> E16[切分 Diff]
    E16 --> E17[发送本地模型服务]
    E17 --> E18[解析并校验 JSON]
    E18 --> E19[blame 归属问题行]
    E19 --> E20[按阈值汇总状态]
    E20 --> E21{通过?}
    E21 -->|是| E22[更新成功基线]
    E21 -->|否| E23[保留原成功基线]
    E22 --> E24[保存 JSON 报告与日志]
    E23 --> E24
  end
  subgraph CODEX["Codex 实际检查流程：线程记录"]
    C1[读取 unity-code-review Skill] --> C2[确定检查时间边界]
    C2 --> C3[查询基线提交与 HEAD]
    C3 --> C4[统计提交、文件和 Diff]
    C4 --> C5[筛选 C# 及高风险模式]
    C5 --> C6[读取相关源码上下文]
    C6 --> C7[沿生命周期和调用链追踪]
    C7 --> C8[核对相关实现与对照逻辑]
    C8 --> C9[提出问题、影响、建议]
    C9 --> C10[记录待确认项与测试缺口]
    C10 --> C11[输出 Markdown 审查结论]
    C11 --> C12[扩大到指定提交区间并重复聚焦审查]
  end
~~~

## 3. 当前工程自动化工作流

1. 调度器或 CLI 接收工程路径、Git 分支、Skill 路径、失败阈值等参数。
2. 加载配置，执行 checkout；若配置远程则 fetch 和 pull --ff-only。
3. 从状态文件读取 last_successful_sha；首次执行回退到昨天 00:00 前最后一次提交。
4. 若当前 SHA 与成功基线一致，生成 skipped 报告。
5. 获取 Git 变更文件和 Diff，只保留 Game/Assets 下的 C# 文件。
6. 校验文件编码，检查 Runtime 代码中的 Editor API 或 Editor 路径。
7. 执行本地确定性检查：GetComponent 热路径、GameObject.Find、tag 比较、更新函数中的 LINQ/分配、TODO/FIXME、布尔命名等。
8. 加载匹配的 AGENTS.md/SKILL.md，生成规则覆盖与本地工具匹配计划。
9. 执行配置中的编译命令。
10. 按 Skill 规则筛选模型范围，切分 Diff。
11. 将 Diff、上下文和 Skill 条款发送给本地模型服务。
12. 要求模型返回 findings、open_questions、test_gaps JSON；每个切片失败最多重试 3 次。
13. 对问题执行 git blame，补充作者和提交 SHA。
14. 根据编译、模型状态和严重级别阈值汇总结果；通过才更新成功基线，同时保存 JSON、Diff、模型输入和日志。

## 4. Codex 实际检查工作流

### 第一轮：近期提交

1. 读取 unity-code-review/SKILL.md。
2. 查询昨晚 12 点前最后提交和当前之后的提交。
3. 确定基线 efabda948，之后 4 个提交。
4. 确认变更集中在月神竞技场 8 个 C# 文件。
5. 阅读 Diff 与相关源码上下文。
6. 搜索弹窗关闭、返回、弹窗栈、挑战次数和按钮状态。
7. 沿 UIManager、UIControler、资料页和竞技场历史项调用顺序追踪。
8. 找到两个问题：资料页关闭回调可能错误重开弹窗；复仇按钮显示与次数校验不一致。
9. 记录待确认项和未执行的 Unity/界面测试。

### 第二轮：指定大范围提交

1. 检查 4abb9695..a844bef9。
2. 统计 308 个提交、约 1482 个变更文件。
3. 排除资源噪声，聚焦手写 C#。
4. 使用 rg 和 Diff 搜索生命周期、订阅、查找、索引、升级请求等模式。
5. 阅读 T18 养成、装备、技能继承和 ResearchManager 上下文。
6. 找到两个问题：技能继承列表重复扫描全量配置表；长按升级固定发送 999 次。
7. 输出问题、影响、建议、待确认项和测试缺口。

## 5. 对比表

| 维度 | 当前工程自动化流程 | Codex 实际流程 |
|---|---|---|
| 触发方式 | 调度器或 CLI | 用户在对话中提出目标 |
| 基线策略 | 持久化 last_successful_sha | 根据时间或指定 SHA 手动确定 |
| Git 同步 | 自动 checkout、可选 fetch/pull | 按任务执行查询 |
| 文件范围 | 固定 Game/Assets/*.cs | 先统计全量，再按风险聚焦 |
| 本地规则 | 白名单检查器自动执行 | 通过 Skill 指导搜索和阅读 |
| Skill 使用 | 自动发现、拆分、匹配 | 先读取 Skill，再组织审查 |
| 编译 | 配置命令自动执行 | 本次未运行 Unity 编译 |
| 模型调用 | 本地 HTTP、结构化 JSON、重试 | Codex 推理和命令执行，输出 Markdown |
| 代码理解 | Diff、规则和有限上下文 | 动态追踪调用链和业务上下文 |
| 结果归属 | 自动 git blame | 输出文件和行号 |
| 结果持久化 | JSON、Diff、输入、日志、状态 | 本次人工整理为 Markdown |
| 成功基线 | 通过才更新 | 不自动更新 |
| 可重复性 | 高，步骤固定 | 中等，依赖搜索和上下文 |
| 业务语义分析 | 主要交给模型规则 | 强，能追踪交互和生命周期 |
| 测试闭环 | 支持配置编译 | 明确记录缺口但本轮未执行 |

## 6. 关键结论

当前工程强在增量基线、确定性检查、编译门禁、结构化输出、失败保护和日志持久化，适合持续运行和发布门禁。

Codex 强在根据中间发现动态改变搜索方向，串联多个文件追踪生命周期和业务语义，适合复杂功能和专项审查。

目前两套流程没有完全闭环：

1. Codex 发现没有自动写回工程 JSON 报告或调度器记录。
2. Codex 没有触发 Unity 编译、玩法测试或成功基线更新。
3. 自动化报告没有自动成为 Codex 的输入上下文。

## 7. 推荐组合流程

~~~mermaid
flowchart TD
  A[调度器触发自动检查] --> B[Git 增量与成功基线]
  B --> C[本地确定性检查]
  C --> D[编译检查]
  D --> E[模型结构化审查]
  E --> F{有高风险或上下文复杂问题?}
  F -->|否| G[生成报告并按结果更新基线]
  F -->|是| H[生成 Codex 专项审查任务]
  H --> I[Codex 读取自动化报告、Diff、Skill]
  I --> J[追踪调用链和业务流程]
  J --> K[输出补充问题、建议和测试用例]
  K --> L[执行编译与玩法测试]
  L --> M[合并自动化结果和 Codex 结果]
  M --> N{全部通过?}
  N -->|是| O[更新成功基线]
  N -->|否| P[保留原成功基线并标记待修复]
~~~
