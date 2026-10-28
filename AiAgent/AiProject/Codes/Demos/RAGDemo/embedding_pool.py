"""
常见向量库
InMemoryStore: 纯内存存储实现，零配置即可启动，无需依赖外部服务。非常适合本地开发调试、单元测试以及对数据持久性要求不高的快速原型验证场景
Chroma: 轻量级嵌入式向量数据库，支持磁盘持久化，部署及其简单。专为中小规模数据设计，是AI应用原型验证、PoC阶段的首选工具
FAISS: Facebook开源的高性能检索库，提供极致的检索速度。支持CPU/GPU加速，专为十亿级大规模向量数据的高效相似度搜索与聚类分析优化
Milvus: 云原生分布式向量数据库，具备企业级高可用与高并发能力。支持动态扩容与多租户管理，是面向生产环境的大规模向量检索标准方案

"""

# pip install langchain-chroma

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(
    model="qwen3-embedding:0.6b"
)

vectorstore = Chroma(
    collection_name="my_knowledge_base",
    embedding_function=embeddings,
    persist_directory="./db/chroma_db"  #持久化目录
)

# 添加文档 (自动完成向量化+存储)
vectorstore.add_documents(chunks)
print(f"知识库共 {len(chunks)} 个片段")

# 相似度检索：
results = vectorstore.similarity_search(
    "高血压饮食注意事项",
    k=3 # 返回 Top-3 最相关的片段
)
for i, doc in enumerate(results):
    print(f"结果 {i+1}: {doc.page_content[:200]}...")

#检索器----------------------------------------------------------------------------------------
retriever = vectorstore.as_retriever(
    search_type = "similarity",
    search_kwargs = {"k": 3}
)

# 后续检索一行代码搞定
docs = retriever.invoke("高血压饮食注意事项")
print(f"检索到{len(docs)} 个相关文档，内容：{docs[0].page_content[:100]}...")