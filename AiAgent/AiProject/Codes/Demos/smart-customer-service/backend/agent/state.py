from typing import TypedDict, Annotated, NotRequired
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: NotRequired[str]
    intent: NotRequired[str]
    order_info: NotRequired[str]