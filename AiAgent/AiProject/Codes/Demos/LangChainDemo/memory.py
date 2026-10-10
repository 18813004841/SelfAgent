from langchain.agents import create_agent
from langchain.messages import HumanMessage, AIMessage
from pathlib import Path
import sys
OPENAI_AGENT_ROOT = Path(__file__).resolve().parents[2] / "Agents" / "OpenAiAgent"
sys.path.insert(0, str(OPENAI_AGENT_ROOT))
from codex_agent.local_model import ChatLocalLLMAgent
#加载环境变量 
from dotenv import load_dotenv

"""
安装dotenv pip install python-dotenv
安装langchain pip install langchain
安装deepseek pip install langchain-deepseek

"""

load_dotenv(Path(__file__).with_name(".env.langchain.demo"))

model = ChatLocalLLMAgent()
agent = create_agent(model=model)

response = agent.invoke({
    "messages": [
        HumanMessage(content="你好我叫张三"),
        AIMessage(content="你好张三，我是一个AI助手，很高兴见到你！"),
        HumanMessage(content="我的名字是什么？")
    ]
})

#优雅的打印整个对话历史
for message in response["messages"]:
    message.pretty_print()