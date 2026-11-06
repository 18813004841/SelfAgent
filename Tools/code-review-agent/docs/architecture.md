# 架构与流程

## 核心流程

~~~mermaid
flowchart TD
    A[读取项目配置] --> B[Git fetch/checkout/pull]
    B --> C[读取 last_successful_sha]
    C --> D[生成增量文件和 diff]
    D --> E[加载 AGENTS.md 与 SKILL.md]
    E --> F[Unity Runtime 边界检查]
    F --> G[执行项目编译命令]
    G --> H[调用本地模型服务]
    H --> I[校验结构化 JSON]
    I --> J[汇总报告]
    J --> K{通过?}
    K -->|是| L[更新成功基线]
    K -->|否| M[保留原成功基线]
~~~

## 边界

`code_review` 不依赖 `OpenAiAgent`，不启动模型服务，不执行模型返回的命令。模型服务只通过 `model_service.py` 的 HTTP 客户端访问。
