#LCEL(LangChain Expression Language) 极简构建
#langchain 连 chain = prompt | llm | StrOutputParser()

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import os

llm = ChatOpenAI(
    base_url = os.getenv("SILICONFLOW_BASE_URL")
    api_key= = os.getenv("SILICONFLOW_API_KEY")
    model="Qwen/Qwen2-8B"
)

prompt = ChatPromptTemplate.from_template("回答关于{topic}的问题：{question}")
qa_chain = prompt | llm | StrOutputParser()

response = qa_chain.invoke({
    "topic": "人工智能",
    "question": "什么是大语言模型？"
})
print(response)

#方式2 RunnableParallel, RunnablePassthrough --------------------------------------------------------------------------
from langchain_core.runnables import RunnableParallel,RunnablePassthrough

def get_context(topic: str) -> str:
    """模拟从数据库或知识库或联网搜索获取上下文"""
    context_map = {
        "人工智能": "人工智能是研究如何使用计算机模拟人类只能的领域...",
        "大语言模型": "大语言模型是指具有数十亿参数的深度学习模型..."
    }
    return context_map.get(topic, f"关于{topic}的通用信息")

prompt = ChatPromptTemplate.from_template(
    "参考上下文: {context}\n回答关于{topic}的问题: {question}"
)

multi_input_chain = (
    RunnableParallel({
        "topic": lambda x: x["topic"],
        "question": lambda x: x["question"],
        "context": lambda x:get_context(x["topic"])
    })
    | prompt
    | llm
    | StrOutputParser()
)

response = multi_input_chain.invoke({
    "topic": "人工智能",
    "question": "什么是大语言模型？"
})

print(response)

#方法2：使用RunnablePassthrough.assign 更简洁（推荐）
multi_input_chain = (
    RunnablePassthrough.assign(
        context=lambda x: get_context(x["topic"])
    )
    | prompt
    | llm
    | StrOutputParser()
)

response = multi_input_chain.invoke({
    "topic": "人工智能",
    "question": "什么是大语言模型？"
})

print(response)

# 多链 -------------------------------------------------------------------------------
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url=os.getenv("SILICONFLOW_BASE_URL"),
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    model="Qwen/Qwen3-8B"
)

# 链1：生成产品名
name_prompt = ChatPromptTemplate.from_template("为{product}起一个简洁的产品名称，只需输出名称")
name_chain = name_prompt | llm | StrOutputParser()

# 链2：生成描述（需要原始输入 + 链1的输出）
desc_prompt = ChatPromptTemplate.from_template(
    "根据产品类型{product}和名称{name}, 写50字描述"
)
# 使用 RunnablePassthrough.assign 串联：先保留原始输入，再追加 name 字段
desc_chain = (
    RunnablePassthrough.assign(name = name_chain) # name_chain 接收原始 product
    | desc_prompt
    | llm
    | StrOutputParser()
)

#最终组合：并行获取两个结果
full_chain = RunnableParallel(
    product_name = name_chain,
    product_description = desc_chain
)

result = full_chain.invoke({"product": "智能手表"}) 

# 条件链 -------------------------------------------------------------------------------------
from langchain_core.runnables import RunnableBranch, RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url=os.getenv("SILICONFLOW_BASE_URL"),
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    model="Qwen/Qwen3-8B"
)

# 定义各专业链
python_prompt = ChatPromptTemplate.from_template(
    "你是Python专家，请用技术术语回答，包含代码示例：\n问题：{question}"
)
python_chain = python_prompt | llm | StrOutputParser()

general_prompt = ChatPromptTemplate.from_template(
    "请简洁回答（不超过100字）：\n问题：{question}"
)
general_chain = general_prompt | llm | StrOutputParser()

# 条件分支
branch_chain = RunnableBranch(
    (lambda x: "python" in x["question"], python_chain),
    (lambda x: "天气" in x["question"], general_chain),
    general_chain
)

# 构建完整链：先通过 RunnablePassthrough 透传，再路由
conditional_chain = (
    RunnablePassthrough.assign(question = lambda x: x)  # 将原始字符串转为字典
    | branch_chain
)

# 构建完整链：先通过 RunnablePassthrogh 透传，再路由
conditional_chain = (
    RunnablePassthrough.assign(question=lambda x: x) # 将原始字符串转化为字典
    | branch_chain
)

# 测试
print(conditional_chain.invoke({"question":"Python中如何反转列表？"}))
print(conditional_chain.invoke({"question":"今天天气怎么样？"}))
print(conditional_chain.invoke({"question":"你好"}))

# 循环链 -----------------------------------------------------------------------------
class IdiomChain:
    """成语接龙--每次用上一个成语作为输入"""
    def __init__(self, llm):
        self.prompt = ChatPromptTemplate.from_template("接龙成语'{prev}的下一个成语是：\n注意：你只需要输出下一个成语，无需解释'")
        self.chain = self.prompt | llm | StrOutputParser()

    def __call__(self, prev_idiom):
        return self.chain.invoke({"prev": prev_idiom})

chain = IdiomChain(llm)
current = "守株待兔"
for _ in range(5):
    current = chain(current)
    print(current)

#重试链 -------------------------------------------------------------------------------
# 方式1：自动重试（指数退避）
prompt = ChatPromptTemplate.from_template("接龙成语'{prev}的下一个成语是：\n注意：你只需要输出下一个成语，无需解释'")
chain = prompt | llm | StrOutputParser()
robust_chain = chain.with_retry(
    stop_after_attempt=3,
    wait_exponential_jitter=True
)

# 方式2：降级回退（主模型失败/超时时切换备用链
newPrompt = ChatPromptTemplate.from_template("链失效'")
backup_chain = newPrompt | llm | StrOutputParser()
fallback_chain = chain.with_fallbacks([backup_chain])

# 结构化输出 ----------------------------------------------------------------------------
import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# 1. 定义结构化输出的数据模型
class ProductInfo(BaseModel):
    name: str = Field(description="创新的产品名称，要求吸引人，不超过10个字")
    price: float = Field(description="预估的市场零售价（单位：元）")
    tags: list[str] = Field(description="产品的3个核心卖点标签")

prompt = ChatPromptTemplate.from_template("接龙成语'{prev}的下一个成语是：\n注意：你只需要输出下一个成语，无需解释'")
structured_chain = prompt | llm.with_structured_output(ProductInfo) | StrOutputParser()
result = structured_chain.invoke({
    "product": "一款能自动检测睡眠脑电波，并在浅睡期释放煮面香薰的智能眼罩"
})

print(f"产品名称：{result.name}")
print(f"预估价格：{result.price}")
print(f"核心标签：{result.tags}")

# 意图识别链 -----------------------------------------------------------------------------
consult_chain = ChatPromptTemplate.from_template("你是客服咨询顾问，请回答：{input}") | llm | StrOutputParser()
complaint_chain = ChatPromptTemplate.from_template("你是投诉处理专员，请妥善处理：{input}") | llm | StrOutputParser()
general_chain = ChatPromptTemplate.from_template("你是一个有好的聊天助手，请回复：{input}") | llm | StrOutputParser()

# 2. 意图识别链（使用结构化输出替代字符串匹配，彻底解决不稳定性）
class IntentResult(BaseModel):
    intent: str = Field(description="用户意图，仅限'咨询'、'投诉'、'闲聊'三者之一")

intent_chain = (
    ChatPromptTemplate.from_template("识别用户意图：\n用户消息：{input}")
    | llm.with_structured_output(IntentResult)
)

# 3. 使用 RunnableBranch 路由（基于结构化字段精确判断）
branch_chain = RunnableBranch(
    (lambda x: x["intent_result"].intent == "投诉", complaint_chain),
    (lambda x: x["intent_result"].intent == "咨询", consult_chain),
    general_chain # 默认
)

customer_service_chain = (
    RunnablePassthrough.assign(
        intent_result = lambda x: intent_chain.invoke({"input": x})
    )
    | branch_chain
)

print(customer_service_chain.invoke({"input":"你们的产品怎么退货？"}))