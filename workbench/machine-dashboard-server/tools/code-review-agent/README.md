# Local Incremental Code Review Agent

本模块用于检查 Unity C# 工程从上一次成功检查到当前分支 HEAD 的代码增量。

## 设计决策

- 不引入 LangChain：当前流程是有限步骤的流水线，标准库更容易控制超时、上下文和失败状态。
- 不依赖 OpenAiAgent：模型客户端只调用本地 HTTP 服务。
- 第一版不强制创建虚拟环境：代码只依赖 Python 标准库；后续增加第三方解析器时再单独隔离。
- 默认使用服务器已登录的 Codex CLI（`codex exec`）在工程目录内完成审查；将 `model_service.backend` 设为 `http` 才使用旧的 OpenAI 兼容 HTTP 服务。
- 模型不可用时检查失败，不更新成功基线。
- 检查正常完成即保存当前提交作为下次基线，即使发现达到通知级别的问题；问题等级只用于筛选通知，不决定任务是否成功。编译检查失败、模型不可用或取消时不更新基线。

## 目录

~~~text
code-review-agent/
  code_review/
    config.py          配置和默认值
    models.py          数据结构和状态
    git.py             Git 增量和基线
    rules.py           AGENTS/SKILL 发现与匹配
    checks.py          Unity C# 确定性检查
    model_service.py   本地模型 HTTP/SSE 客户端
    pipeline.py        检查编排
    cli.py             命令行入口
  config.example.yaml  配置示例（JSON 语法，零第三方依赖）
  docs/architecture.md 架构和流程图
  requirements.txt    当前为空，保留依赖入口
~~~

## 快速开始

~~~powershell
cd workbench/machine-dashboard-server/tools/code-review-agent
python -m code_review.cli init --project E:/Projects/MyUnity --branch main
python -m code_review.cli check --config config.json
~~~

第一版配置使用 JSON，避免在默认环境中要求 PyYAML。模型服务器需要支持 `POST /v1/chat/completions`，流式响应使用标准 SSE，并以 `data: [DONE]` 结束。

## 检查范围

只报告上次成功基线到当前快照之间，Game/Assets 目录下 .cs 脚本新增或修改的行；合并进入当前分支且体现在这段差异中的内容也包含在内。原有未修改的行不进入问题报告或通知；删除行和没有变更行定位的问题不报告。检查器仍可读取文件上下文，编译检查仍按配置执行。

第一版确定性检查：

- Git 增量是否可获取；
- C# Runtime 代码是否引用 `UnityEditor`；
- Runtime 路径是否引用 Editor 目录或程序集；
- 工程内匹配的 `SKILL.md` 和规则是否加载；
- 配置中声明的编译命令是否执行成功。

其他规范交给工程内 Skill 和本地模型审查。

报告默认使用 Git blame 获取问题所在行的修改人和提交 SHA；无法定位时字段为空并附带警告。大型仓库如需关闭归属查询，可在配置的 `checks` 中设置 `"enrich_attribution": false`。

代码检查可通过飞书群机器人发送通知。可在代码检查页面设置目标群机器人的 Webhook，保存在服务端用户配置目录；尚未通过页面配置时兼容环境变量 `WORKBENCH_CODE_REVIEW_FEISHU_WEBHOOK`，页面清除会禁用该后备地址。还需安装 `lark-cli`，以运行服务的系统账号授权 `contact:user:search`。通知用 Git blame 的作者邮箱精确匹配通讯录，然后在问题旁 @ 对应人员；未匹配时尝试 @ `bo.feng@funplus.com` 并保留原提交人信息，匹配失败会写入报告警告。机器人需要允许发送包含“代码规范检查报告”的消息；用户 ID 的应用适用范围及群内 @ 效果需在目标环境确认。未配置、查询失败或发送失败不会改变检查结论或成功基线，原因显示在报告警告中。凭据不要写入仓库。

任务结束时，无论检查通过、未通过、没有新提交、执行失败或取消，都会尝试发送包含任务名称和状态的消息。仅列出达到失败阈值的问题并 @ 提交人或兜底人员，消息中的问题数量也只统计这些问题。

