from langchain.agents import create_agent
from langchain.tools import tool
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

@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气信息"""
    return f"{city}的天气是晴天，温度25°C"

model = ChatLocalLLMAgent()
agent = create_agent(model=model, tools=[get_weather])

#3. 使用 Agent：create_agent 返回 LangGraph，使用 invoke() 调用
if __name__ == "__main__":
    result = agent.invoke({
        "messages": [{"role": "user", "content": "请告诉我北京的天气。"}]
    })
    print(result["messages"][-1].content)
