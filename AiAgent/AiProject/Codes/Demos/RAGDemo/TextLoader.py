# pip install langchain-community ---------------------------------------------------------------------------
from langchain_community.document_loaders import TextLoader

loader = TextLoader("./docs/test.txt", encoding="utf-8")
docs = loader.load()
print(f"加载 {len(docs)} 个文档，内容：{docs[0].page_content[:100]}")

#pip install bs4 ---------------------------------------------------------------------------------------------
from langchain_community.document_loaders import WebBaseLoader

loader = WebBaseLoader(web_paths=["https//docs.langchain.com/oss/python/langchain/rag"])
docs = loader.load()
print(f"来源：{docs[0].metadata.get('source')}, 长度：{len(docs[0].page_content)} 字符")

#csv loader ----------------------------------------------------------------------------------------------------
from langchain_community.document_loaders.csv_loader import CSVLoader

loader = CSVLoader(file_path="./docs/cozev2_template_agent.csv", source_column="input", encoding="utf-8")
docs = loader.load()
for doc in docs:
    print(f"[{doc.metadata.get('source')}] {doc.page_content[:100]}")

#批量加载 pip install pypdf --------------------------------------------------------------------------------------
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader

loader = DirectoryLoader(
    path="docs/",
    glob="**/*.pdf",
    loader_cls=PyPDFLoader,
    show_progress=True,
    use_multithreading=True
)
documents = loader.load()

#复杂文档处理：MinerU -------------------------------------------------------------------------------------------
"""
pip install langchain-mineru

原生支持PDF、Word、PPT、Excel、HTML、图片等 10+ 格式
精准识别表格、公式(转LaTeX)，复杂多栏排版
提供公共API(每天免费5000个文档)，可本地部署
LangChain 原生集成，输出即为 Document 对象

安装与配置：在 .env中配置 MINERU_TTOKEN (官网 https://mineru.net 免费申请)
"""
from langchain_mineru import MinerULoader

loader = MinerULoader(
    source="./docs/老年健康指南.pdf",
    mode="flash",   # flash (免登录，<20页) 或 precision (需token, <200页)
)
docs = loader.load() #直接返回 LangChain Document 对象
print(docs[0].metadata)
print(docs[0].page_content[:500])

#处理扫描件（OCR）
loader = MinerULoader(
    source="./docs/test.jpg",
    mode="precosion",
    ocr=True    #开启 OCR 识别扫描件中的文字
)
docs = loader.load() #直接返回 LangChain Document 对象
print(docs[0].metadata)
print(docs[0].page_content[:500])