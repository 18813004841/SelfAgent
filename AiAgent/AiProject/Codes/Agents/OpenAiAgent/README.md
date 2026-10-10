# OpenAI Codex OAuth Agent

一个最小但可运行的 Python CLI Agent：使用 OAuth 设备码登录，安全保存并刷新令牌，然后通过 Codex Responses 接口进行多轮对话。

> 说明：OpenAI/Codex 的 OAuth 和订阅接口可能随官方客户端版本调整。本项目将 OAuth 与模型端点全部做成环境变量，可在接口变更时替换，不把令牌写入项目目录。

## 安装

本工程统一使用 Conda 环境 `self_agent_env`，不要使用项目目录中的 `.venv`。

如果环境尚未创建：

```bash
conda env create -f environment.yml
```

激活并安装本地工程：

```bash
conda activate self_agent_env
python -m pip install -e ".[test]"
```

## 登录

```bash
codex-agent login
```

命令会显示验证地址和一次性代码。请在浏览器完成 ChatGPT/Codex 授权。令牌默认保存到：

```text
~/.self_agent/.codex-agent/auth.json
```

Windows 默认路径为：

```text
C:\Users\<当前用户>\.self_agent\.codex-agent\auth.json
```

也可以通过 `CODEX_TOKEN_PATH` 修改。

## LangChain 本地模型网关

安装 LangChain 集成：

```bash
conda activate self_agent_env
python -m pip install -e ".[langchain]"
```

启动本地网关：

```bash
python -m codex_agent.openai_gateway
```

网关默认监听 `http://127.0.0.1:8765/v1`，读取本机已经保存的 OAuth token，
不需要把 access token 或 refresh token 写进 `.env`。

LangChain 使用 `ChatLocalLLMAgent`，工具、记忆、缓存和中间件仍由 LangChain
管理：

```python
from langchain.agents import create_agent
from langchain.tools import tool
from codex_agent.local_model import ChatLocalLLMAgent


@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气信息"""
    return f"{city}：晴天，25°C"


agent = create_agent(
    model=ChatLocalLLMAgent(),
    tools=[get_weather],
)
result = agent.invoke({
    "messages": [{"role": "user", "content": "北京天气怎么样？"}]
})
print(result["messages"][-1].content)
```

配置变量：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `LOCALLLMAGENT_API_KEY` | `local-only` | 本地网关占位 key，不是真实 OAuth token |
| `LOCALLLMAGENT_API_URL` | `http://127.0.0.1:8765/v1` | 本地网关地址 |
| `LOCALLLMAGENT_MODEL` | `gpt-5.6-sol` | Codex 模型名 |
| `CODEX_GATEWAY_PORT` | `8765` | 网关监听端口 |

请求链路为：

```text
LangChain ChatLocalLLMAgent
        ↓
本地 /v1/chat/completions
        ↓
codex_agent.openai_gateway
        ↓
Codex OAuth Responses API
```

网关支持普通聊天、工具调用、`ToolMessage`、多轮消息和 Chat Completions SSE
响应。当前 SSE 是在 Codex 完整响应返回后转换并发送，格式兼容 LangChain 的
`stream()`/`astream()`，还不是上游 Codex 的逐 Token 实时转发。网关只绑定
`127.0.0.1`，不要直接暴露到公网。

## 对话

```bash
codex-agent chat
codex-agent chat "解释 OAuth 和 API Key 的区别"
```

环境变量：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `CODEX_MODEL` | `gpt-5.6-sol` | 模型名 |
| `CODEX_BASE_URL` | `https://chatgpt.com/backend-api/codex` | Codex 服务基础地址 |
| `CODEX_OAUTH_DEVICE_URL` | `https://auth.openai.com/api/accounts/deviceauth/usercode` | 设备码申请地址 |
| `CODEX_OAUTH_DEVICE_TOKEN_URL` | `https://auth.openai.com/api/accounts/deviceauth/token` | 设备码轮询地址 |
| `CODEX_OAUTH_TOKEN_URL` | `https://auth.openai.com/oauth/token` | 授权码/刷新令牌地址 |
| `CODEX_CLIENT_ID` | `app_EMoamEEZ73f0CkXaXp7hrann` | Codex 官方 OAuth 客户端 ID |
| `CODEX_TOKEN_PATH` | `~/.self_agent/.codex-agent/auth.json` | 本地凭证文件 |
| `CODEX_HTTP_TIMEOUT` | `60` | HTTP 请求超时时间（秒） |
| `CODEX_POLL_INTERVAL` | `5` | OAuth 设备码轮询间隔（秒） |

## 安全

- 不要提交 `auth.json`。
- Access Token 过期后，客户端会用 Refresh Token 自动刷新。
- 令牌文件会尝试设置为仅当前用户可读写的权限。
- 生产环境建议使用操作系统密钥环或系统凭据管理器替代文件存储。

## 测试

```bash
conda activate self_agent_env
python -m pytest
```
