from mcp.server.fastmcp import FastMCP

mcp = FastMCP("OrderService")

orders_db = {
    "ORD001": {"status": "已发货", "tracking": "SF1234567890", "product": "无线耳机"},
    "ORD002": {"status": "配送中", "tracking": "JD9876543210", "product": "智能手表"},
    "ORD003": {"status": "已签收", "tracking": "YT5555555555", "product": "笔记本电脑"},
}

@mcp.tool()
def get_order(order_id: str) -> dict:
    """查询订单详情"""
    return orders_db.get(order_id, {"error": f"订单 {order_id} 不存在"})

@mcp.tool()
def list_orders(user_id: str) -> list:
    """列出用户所有订单（模拟）"""
    return [{"order_id": k, "product": v["product"], "status": v["status"]} 
            for k, v in orders_db.items()]

if __name__ == "__main__":
    mcp.run(transport="stdio")