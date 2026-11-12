"""页面接口层。每个 web 页面对应一个模块，集中声明其 API 路由。"""
from .router import ViewRouter, ViewContext

router = ViewRouter()

