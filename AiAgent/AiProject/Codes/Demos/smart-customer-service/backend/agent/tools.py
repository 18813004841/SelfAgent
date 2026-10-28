import asyncio
import os
import sys
from pathlib import Path
from langchain.tools import tool
from dotenv import load_dotenv
load_dotenv()

# ``backend/mcps`` is the demo's server package, but running ``main.py`` puts
# ``backend`` first on sys.path and makes it shadow the installed MCP SDK.
# Remove that one path while importing the adapter, then restore sys.path.
_backend_dir = str(Path(__file__).resolve().parents[1])
_saved_sys_path = sys.path[:]
try:
    sys.path = [p for p in sys.path if str(Path(p or ".").resolve()) != _backend_dir]
    from langchain_mcp_adapters.client import MultiServerMCPClient
finally:
    sys.path = _saved_sys_path

@tool
def search_knowledge_base(query: str) -> str:
    """搜索产品知识库，回答用户咨询问题"""
    knowledge_base = {
        "退货政策": "7天无理由退货，需保持商品完好，运费由买家承担",
        "换货政策": "15天内可换货，需提供质检报告",
        "保修政策": "整机保修1年，配件保修3个月",
        "配送时间": "一线城市次日达，其他地区3-5天",
        "退款时间": "退款审核通过后3-7个工作日到账",
    }

    for key, value in knowledge_base.items():
        if key in query or query in key:
            return value
    return f"未找到关于'{query}'的相关信息，请转人工客服。"

def get_mcp_tools():
    """获取MCP工具（同步包装）"""
    async def _get_tools():
        client = MultiServerMCPClient({
            "orders":{
                "transport": "stdio",
                # Use the current interpreter so the MCP subprocess sees the
                # same environment as the API process (especially on Windows).
                "command": sys.executable,
                # The MCP server lives in the sibling ``mcps`` package.
                "args": [str(Path(__file__).resolve().parents[1] / "mcps" / "order_server.py")]
            }
        })
        return await client.get_tools()
    
    try:
        return asyncio.run(_get_tools())
    except Exception as e:
        print(f"Failed to connect to MCP server: {e}")
        return []

mcp_tools = get_mcp_tools()
