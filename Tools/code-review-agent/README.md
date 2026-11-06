# Local Incremental Code Review Agent

本模块用于检查 Unity C# 工程从上一次成功检查到当前分支 HEAD 的代码增量。

## 设计决策

- 不引入 LangChain：当前流程是有限步骤的流水线，标准库更容易控制超时、上下文和失败状态。
- 不依赖 OpenAiAgent：模型客户端只调用本地 HTTP 服务。
- 第一版不强制创建虚拟环境：代码只依赖 Python 标准库；后续增加第三方解析器时再单独隔离。
- 模型服务默认地址为 `http://127.0.0.1:8765/v1`，模型为 `gpt-5.6-sol`。
- 模型不可用时检查失败，不更新成功基线。

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
cd Tools/code-review-agent
python -m code_review.cli init --project E:/Projects/MyUnity --branch main
python -m code_review.cli check --config config.json
~~~

第一版配置使用 JSON，避免在默认环境中要求 PyYAML。模型服务器需要支持 `POST /v1/chat/completions`，流式响应使用标准 SSE，并以 `data: [DONE]` 结束。

## 检查范围

第一版确定性检查：

- Git 增量是否可获取；
- C# Runtime 代码是否引用 `UnityEditor`；
- Runtime 路径是否引用 Editor 目录或程序集；
- 工程内匹配的 `SKILL.md` 和规则是否加载；
- 配置中声明的编译命令是否执行成功。

其他规范交给工程内 Skill 和本地模型审查。
