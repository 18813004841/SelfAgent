# LangChain 接入

在 OpenAiAgent 目录安装可选依赖：

```sh
pip install -e ".[langchain]"
```

沿用现有登录信息（先执行 `codex-agent login`），不需要另一套 API Key。

```python
from langchain.agents import create_agent
from codex_agent.langchain_model import CodexChatModel

model = CodexChatModel()  # 使用 Settings.from_env()；也可传 client=现有 CodexClient
print(model.invoke("你好").content)

agent = create_agent(model=model, tools=[], system_prompt="你是中文助手。")
result = agent.invoke({"messages": [{"role": "user", "content": "你好"}]})
print(result["messages"][-1].content)

# 多轮聊天：将上一次完整消息列表传回来。
result = agent.invoke({
    "messages": result["messages"] + [{"role": "user", "content": "继续解释"}]
})
```

支持标准 invoke/ainvoke、消息历史、Runnable 组合、LangChain 回调和工具调用。
历史由调用方或 LangGraph 管理，不使用 Conversation.ask() 重复保存。
stream/astream 通过基类回退返回一次完整回复，不是真正逐 Token 输出。
当前仍只接受文本消息；多模态消息和 stop 参数尚未接入。

该模块按需导入，不影响未安装 LangChain 时原有 CLI 的使用。
