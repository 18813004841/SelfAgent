# 本地机器工作台服务

## 目录结构

- `src/`：核心 Python 服务代码
- `web/`：工作台前端页面
- `config/`：配置模板和环境变量说明
- `logs/`：运行日志目录（默认不提交日志内容）
- `plugins/`：可选插件扩展目录
- `tools/`：运维和开发辅助工具
- `scripts/`：启动、检查等自动化脚本

## 启动

```bash
sh start.sh
```

访问 `http://127.0.0.1:18888`。

可通过 `MACHINE_DASHBOARD_PORT` 修改端口。
