# 服务器 Codex 部署

代码检查服务器使用已登录的 Codex CLI，不启动单独的模型 HTTP 服务，也不依赖客户机 Local Agent。

## 安装与登录

在运行 `machine-dashboard-server` 的服务器上安装 Codex CLI，并用执行代码检查的服务账号完成登录。验证：

```powershell
codex --version
codex login status
```

服务器账号需要能够读取目标工程、执行 Git 查询和运行配置中的编译命令。代码检查通过 `codex exec` 使用只读沙箱和 `--ask-for-approval never`，Codex 不应修改工程。

## 配置

在代码检查配置的 `model_service` 中使用：

```json
{
  "backend": "codex",
  "executable": null,
  "model": null,
  "sandbox": "read-only",
  "timeout_seconds": 900
}
```

`executable` 为空时从服务器 PATH 查找 `codex`（Windows 优先查找 `codex.cmd`）。需要固定安装路径时填写绝对路径。`model` 为空时使用 Codex 配置中的默认模型。

## 运行与故障处理

调度器先执行 Git 同步、确定性检查和编译，再启动 Codex。Codex 输出必须包含约定的 JSON 对象；进程非零退出、超时、取消或输出格式错误都会使本次检查失败，并保留上一次成功基线。

服务器不应把 API Key 写入任务参数、日志或报告。日志记录执行状态、耗时和错误摘要；报告由工作台用户数据目录统一保存。

旧的 OpenAI 兼容 HTTP 后端仍可通过 `"backend": "http"` 使用，便于回滚和对比验证。
