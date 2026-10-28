from langchain_deepseek import ChatDeepSeek
from langchain.chat_models import init_chat_model
from pathlib import Path
# 加载环境变量
from dotenv import load_dotenv
from langchain.agents import create_agent
import os

env_path = Path(__file__).parent / ".env.langchain.demo"
load_dotenv(env_path)

# LangChain 自动识别 DeepSeek, 从环境变量读取 API Key
chat_model = init_chat_model("deepseek-chat")

chat_model = init_chat_model(
    model="deepseek-chat",
    temperature=0.7,    # 随机性 (0-1, 越高越随机)
    max_tokens=150,     # 最大输出长度
    top_p=0.9,          # 采样概率 (0-1, 越低越保守)
    base_url=os.getenv("DEEPSEEK_API_URL"),  # 如果不传入，则从环境变量读取
    api_key=os.getenv("DEEPSEEK_API_KEY")  # 如果不传入，则从环境变量读取
    )

model = ChatDeepSeek(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),  # 如果不传入，则从环境变量读取
    temperature=0.7,    # 随机性 (0-1, 越高越随机)
    max_tokens=150,     # 最大输出长度
    top_p=0.9,          # 采样概率 (0-1, 越低越保守)
    )

response = model.invoke("请用中文介绍一下深寻科技。")
#流式
for chunk in model.stream("请用中文介绍一下深寻科技。"):
    print(chunk.content, end="", flush=True)

#agent 中使用模型
agent_response = create_agent(model=model, tools=[])
agent_response = create_agent(model="deepseek-chat", tools=[])

response = agent_response.invoke("请用中文介绍一下深寻科技。")
#流式
for token, metadata in agent_response.stream(
    {"messages":[{"role":"user","content":"请用中文介绍一下深寻科技。"}]},
    stream_mode="messages"
    ):
    if token.content:
        print(token.content, end="", flush=True)