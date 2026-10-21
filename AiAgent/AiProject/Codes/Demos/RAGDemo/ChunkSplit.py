from langchain_text_splitters import RecursiveCharacterTextSplitter #递归字符文档分割
from langchain_mineru import MinerULoader

loader = MinerULoader(
    source="./docs/老年健康指南.pdf",
    mode="flash",
)
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,    # 目标块大小（字符数）
    chunk_overlap=200,  #中间堆叠（10%-20%）
    separators=["\n\n", "\n", "。", "！", "？", "：", "，", " ", ""]    # 优先级从高到低
)

chunks = splitter.split_documents(docs)
print(f"原始文档数：{len(docs)}, 切分后块数：{len(chunks)}")

"""
参数建议：
chunk_size: 200~1000，取决于模型上下文长度和文档密度
chunk_overlap: chunk_size 的 10%~20%
separators: 中文文档建议加入中文标点 (。！？；，)
"""

# 结构感知切分 ----------------------------------------------------------------------------------

from langchain_text_splitters import MarkdownHeaderTextSplitter

markdown_text = """
# 第一章
## 1.1
###1.1.1
...
"""

headers_to_split=[
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3"),
]
splitter = MarkdownHeaderTextSplitter(headers_to_split)
chunks = splitter.split_text(markdown_text)

for doc in chunks:
    print(f"{doc.metadata} -> {doc.page_content[:80]}...")

# 固定长度切分 ---------------------------------------------------------------------------------

long_text = " ... "

from langchain_text_splitters import CharacterTextSplitter
splitter = CharacterTextSplitter.from_huggingface_tokenizer(
    encoding_name = "cl100k_base",  # 使用 cl100k_base 编码 （对应 GPT-4 等模型）
    chunk_size=500,                 # 每个块的最大 token 数
    chunk_overlap=50                # 块之间的重叠 token 数
)
chunks = splitter.split_text(long_text)