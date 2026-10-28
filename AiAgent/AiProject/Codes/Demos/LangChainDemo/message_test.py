from langchain.agents import create_agent
from langchain.messages import HumanMessage, AIMessage
from pathlib import Path
import sys
OPENAI_AGENT_ROOT = Path(__file__).resolve().parents[2] / "Agents" / "OpenAiAgent"
sys.path.insert(0, str(OPENAI_AGENT_ROOT))
from codex_agent.local_model import ChatLocalLLMAgent
#加载环境变量 
from dotenv import load_dotenv

from langchain_core.prompts import(
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

"""
安装dotenv pip install python-dotenv
安装langchain pip install langchain
安装deepseek pip install langchain-deepseek

"""

load_dotenv(Path(__file__).with_name(".env.langchain.demo"))

model = ChatLocalLLMAgent()
agent = create_agent(model=model)


#定义角色和用户输入
system_message = SystemMessagePromptTemplate.from_template(
    "你是以为自身的{role}，用{style}的风格和用户进行对话。"
    )

human_message = HumanMessagePromptTemplate.from_template(
    "用户输入：{user_input}"
    )

#组合成一个聊天提示模板
chat_prompt = ChatPromptTemplate.from_messages(
    [system_message, human_message]
    )

#格式化
messages = chat_prompt.format_messages(
    role="AI助手",
    style="专业严谨",
    user_input="如何理解 transformer 模型的自注意力机制？"
    )

for message in messages:
    if isinstance(message, HumanMessage):
        print(f"Human: {message.content}")
    elif isinstance(message, AIMessage):
        print(f"AI: {message.content}")