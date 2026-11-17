# 工作台项目规则

- 工作台负责页面、HTTP API、调度、进程编排、配置和自身数据库。
- AiAgent 与 machine-control 通过 HTTP、CLI、协议或 launcher 集成，禁止反向导入其业务实现或直接读取其数据库。
- 运行产物写入用户级 `LocalWorkbench`；源码目录仅保留模板和测试夹具。
- `machine-dashboard-client` 是工作台客户机侧独立运行单元；它只监听回环地址，负责浏览器所在机器的本地路径、中央客户端和本地 Codex。服务端页面通过明确的 Local Agent HTTP 契约调用它。
- 新入口、配置、表结构和跨项目接口必须更新架构文档、模块规则和验证脚本。
