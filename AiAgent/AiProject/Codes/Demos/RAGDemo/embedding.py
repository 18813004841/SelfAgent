# 安装ollama: pip install langchain_ollama
# 拉取模型: ollama pull qwen3-embedding:0.6b

from langchain_ollama import OllamaEmbeddings

embeddings = OllamaEmbeddings(
    model="qwen3-embedding:0.6b"
)

# 单条向量化
vec = embeddings.embed_query("我不爱上班")
print(f"维度：{len(vec)}")

# 批量向量化
vectors = embeddings.embed_documents(["我要躺平", "我不爱工作", "拒绝上班"])
print(f"批量：{len(vectors)}条，维度：{len(vectors[0])}")


#验证语义相似度：
import numpy as np

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

base_vec = embeddings.embed_query("我不爱上班")
for text, vec in zip(["我要躺平"], vectors):
    sim = cosine_similarity(base_vec, vec)
    print(f"{text} 与 我不爱上班 相似度：{sim:.4f}")


# 云端 Embedding -------------------------------------------------------------------------------------------------
# pip install dashscope
import os
from langchain_community.embeddings import DashScopeEmbeddings #阿里云百炼的案例

dashscope_embeddings = DashScopeEmbeddings(
    model="text-embedding-v3",
    dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")    #需要在.env文件中写入 DASHSCOPE_API_KEY
)

#向量化单条文本
text = "我爱上班"
vector = dashscope_embeddings.embed_query(text)

print(f"文本：{text}")
print(f"向量维度：{len(vector)}")
print(f"向量前5维：{len(vector[:5])}")

# 批量向量化
texts = ["我要躺平", "我爱工作", "拒绝加班"]
vectors = dashscope_embeddings.embed_documents(texts)
print(f"\n批量向量化：{len(vectors)} 条，维度：{len(vectors[0])}")

for v in vectors:
    similarity = cosine_similarity(vector, v)
    print("Cosine Similarity:", similarity)