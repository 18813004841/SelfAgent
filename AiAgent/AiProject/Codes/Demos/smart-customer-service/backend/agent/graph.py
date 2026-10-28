from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from .tools import search_knowledge_base, mcp_tools
from .state import AgentState
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# ``codex_agent`` lives in Codes/Agents/OpenAiAgent, outside this demo's
# backend package. Make direct ``python backend/main.py`` execution work too.
_openai_agent_root = Path(__file__).resolve().parents[4] / "Agents" / "OpenAiAgent"
if str(_openai_agent_root) not in sys.path:
    sys.path.insert(0, str(_openai_agent_root))

from codex_agent.openai_gateway import create_chat_model
load_dotenv()

logger = logging.getLogger(__name__)

local_tools = [search_knowledge_base]
all_tools = local_tools + mcp_tools
tools_by_name = {t.name: t for t in all_tools}

model = create_chat_model()
model_with_tools = model.bind_tools(all_tools)

SYSTEM_PROMPT = """你是一个智能客服助手。请根据用户意图选择合适的工具：
- 如果用户询问产品政策、使用方法等，使用 search_knowledge_base
- 如果用户查询订单，使用 get_order 或 list_orders（来自MCP服务）
- 如果用户要求退货或换货，先查询订单状态再给出建议
- 如果问题复杂无法处理，直接告知用户并建议转人工

请用友好、专业的语气回答。"""

def llm_node(state: AgentState):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    logger.info("LLM 请求: message_count=%d, last_message=%s", len(messages), messages[-1].content)
    response = model_with_tools.invoke(messages)
    logger.info(
        "LLM 响应: content=%s, tool_calls=%s",
        response.content,
        getattr(response, "tool_calls", None),
    )
    return {"messages": [response]}

async def tool_node(state: AgentState):
    last_message = state["messages"][-1]
    results = []
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool = tools_by_name.get(tool_call["name"])
            if tool:
                try:
                    # 使用异步调用
                    result = await tool.ainvoke(tool_call["args"])
                    results.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
                except Exception as e:
                    results.append(ToolMessage(content=f"工具执行错误: {str(e)}", tool_call_id=tool_call["id"]))
            else:
                results.append(ToolMessage(content=f"工具 {tool_call['name']} 不可用", tool_call_id=tool_call["id"]))
    return {"messages": results}

def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    return END

def create_agent():
    graph = StateGraph(AgentState)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", should_continue)
    graph.add_edge("tools", "llm")
    return graph.compile(checkpointer=InMemorySaver())

agent = create_agent()
