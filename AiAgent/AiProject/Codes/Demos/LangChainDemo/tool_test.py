from langchain.tools import tool
from langchain.agents import create_agent

# 1. 用@tool装饰器定义一个工具函数
@tool
def get_weather(location: str) -> str:
    """获取指定位置的天气信息"""
    # 这里可以调用实际的天气API来获取天气信息
    return f"{location}的天气是晴天，温度25摄氏度。"

@tool("square_root", description="计算一个数字的平方根")
def tool_square_root(number: float) -> float:
    """计算一个数字的平方根"""
    import math
    return math.sqrt(number)

# 2. 创建 Agent 并注册工具
agent = create_agent(
    model="deepseek-chat",  # 使用 DeepSeek 模型
    tools=[get_weather, tool_square_root]
)

# 3. 调用--Agent 会自动判断需要调用 get_weather 工具
response = agent.invoke({
    "messages": [
        {"role": "system", "content": "你是一个天气助手。"},
        {"role": "user", "content": "请告诉我北京的天气。"}
    ]
})

for msg in response["messages"]:
    msg.pretty_print()  # 打印消息内容


#注意 LangChain 中工具函数有两个保留参数名不能使用 -- config (运行时配置) 和 runtime (运行时上下文)