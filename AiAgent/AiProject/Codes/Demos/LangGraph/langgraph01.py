# pip install langchain dotenv langchain-deepseek

from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph,START,END    # state start end
from langgraph.graph.message import add_messages,MessagesState  #消息管理
from langgraph.checkpoint.memory import InMemorySaver   #记忆
from langgraph.types import Command, CachePolicy, interrupt #
from langgraph.runtime import Runtime
from langgraph.types import RetryPolicy, TimeoutPolicy
from langgraph.errors import NodeError

from langchain_core.messages import(
    BaseMessage, SystemMessage, HumanMessage, ToolMessage
)
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from IPython.display import Image, display
from operator import add
from dotenv import load_dotenv
from pydantic.dataclasses import dataclass
load_dotenv()

# 常规写法 -------------------------------------------------------------------------------------
# 1. State: 定义共享数据结构
class SimpleState(TypedDict):
    name: str
    greeting: str

# 2. Node: 定义处理逻辑
def greet_node(state: SimpleState):
    print(f"接收名字：{state['name']}")
    return {"greeting": f"Hello, {state['name']}"}

def uppercase_node(state: SimpleState):
    print(f"接收问候语：{state['greeting']}")
    return {"greeting": state["greeting"].upper()}

# 3. Edge: 编排执行顺序
# 3.1 用State创建图
graph_builder = StateGraph(SimpleState)
# 3.2 注册节点node
graph_builder.add_node("greet", greet_node)
graph_builder.add_node("uppercase", uppercase_node)
# 3.3 创建edge，链接各个节点 
graph_builder.add_edge(START, "greet")
graph_builder.add_edge("greet", "uppercase")
graph_builder.add_edge("uppercase", END)
# 3.4 编译成可执行图
graph = graph_builder.compile()

# 自定义 reducer 与 快捷stategraph -------------------------------------------------------------------------------------
class CustomReducerState(TypedDict):
    count: int                          # 这个字段没有定义Reducer，也就是默认会覆盖旧值
    nodes: Annotated[list[str], add]    # 这里使用add作为Reducer，也就是会拼接结果

def node_1(state: CustomReducerState):
    print(f"节点1接收count: {state['count']}")
    return {"count": 1, "nodes": ["node_1"]} # 直接修改nodes值，不用自己拼接

def node_2(state: CustomReducerState):
    print(f"节点2接收count: {state['count']}")
    return {"count": 2, "nodes": ["node_2"]} # 直接修改nodes值，不用自己拼接

graph = (
    StateGraph(SimpleState)
    .add_node("node_1", node_1)
    .add_node("node_2", node_2)
    .add_edge(START, "node_1")
    .add_edge("node_1", "node_2")
    .add_edge("node_2", END)
    .compile()
)

# 执行（必须传入初始化的 State）
result = graph.invoke(CustomReducerState(count=0, nodes=[])) 

# 绘制流程图
display(Image(graph.get_graph().draw_mermaid_png()))

# 并行图 -------------------------------------------------------------------------------------
class ParallelState(TypedDict)：
    nodes: Annotated[list[str], add]

def node_a(state: ParallelState):
    print(f"执行a节点：{state['nodes']}")
    return {"nodes": ["a"]}

def node_b(state: ParallelState):
    print(f"执行a节点：{state['nodes']}")
    return {"nodes": ["b"]}

def node_c(state: ParallelState):
    print(f"执行a节点：{state['nodes']}")
    return {"nodes": ["c"]}

def node_d(state: ParallelState):
    print(f"执行a节点：{state['nodes']}")
    return {"nodes": ["d"]}

# a -> b & c 同时执行 -> d
paralle_graph = (
    StateGraph(ParallelState)
    .add_node("a", node_a)
    .add_node("b", node_b)
    .add_node("c", node_c)
    .add_node("d", node_d)
    .add_edge(START, "a")
    .add_edge("a", "b")
    .add_edge("a", "c")
    .add_edge("b", "d")
    .add_edge("c", "d")
    .add_edge("d", END)
    .compile()
)

# 条件图 -------------------------------------------------------------------------------------
class RouteState(TypedDict):
    score: int
    result: str

def scorer(state: RouteState):
    score = int(input("请输入分数:"))
    print(score)
    return {"score": score}

def pass_node(state: RouteState):
    return {"result": "通过！"}

def fail_node(state: RouteState):
    return {"result": "不通过！"}

def router(state: RouteState) -> Literal["pass", "fail"]:
    """根据score决定下一节点"""
    if state["score"] >= 60:
        return "pass"
    else:
        return "fail"

condition_graph = (
    StateGraph(RouteState)
    .add_node("scorer", scorer)
    .add_node("pass", pass_node)
    .add_node("fail", fail_node)
    .add_node("router", router)
    .add_edge(START, "scorer")
    .add_conditional_edges("scorer", "router")
    .add_edge("pass", END)
    .add_edge("fail", END)
    .compile()
)

result = condition_graph.invoke({"score": 0, "result": ""})