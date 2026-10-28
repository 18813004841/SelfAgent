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

#-- 提示词工程用法

# !!! 提示词导入工程 !!!
from langchain_core.prompts import(
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

model = ChatLocalLLMAgent()
agent = create_agent(
    model=model,
    system_prompt=SystemMessagePromptTemplate.from_template(
        "你是以为自身的{role}，用{style}的风格"
    )
)

system_template = SystemMessagePromptTemplate.from_template(
    "你是以为自身的{role}，用{style}的风格和用户进行对话。"
    )

user_template = HumanMessagePromptTemplate.from_template(
    "用户输入：{user_input}" 
    )

chat_prompt = ChatPromptTemplate.from_messages(
    [system_template, user_template]
    )

msgs = chat_prompt.format_messages(
    role="AI助手",
    style="专业严谨",
    user_input="如何理解 transformer 模型的自注意力机制？"
)

#--  Pydantic 定义输出格式，无需在Prompt中手写 Json 描述
from pydantic import BaseModel

class CapitalInfo(BaseModel):
    name: str
    location: str
    vibe: str
    economy: str

class CapitalInfoOutputInfo(BaseModel):
    name: str
    location: str
    vibe: str
    economy: str

agent = create_agent(
    model=model,
    system_prompt=SystemMessagePromptTemplate.from_template(
        "你是以为自身的{role}，用{style}的风格"
    ),
    response_format=CapitalInfo
    output_schema=CapitalInfoOutputInfo
)
