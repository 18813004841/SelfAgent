---
name: workbench-ui-flow
description: 为工作台新增或修改界面功能，接通 HTML 控件、页面 JavaScript、Python view 路由和业务函数，适用于设置读取回填、参数保存、按钮执行和状态展示。
---

# 工作台界面到 Python

使用前读取目标仓库的 AGENTS.md 和开发规范。先确认页面与服务框架；当前仓库工作台根目录为 workbench/machine-dashboard-server。复用已有路由和持久化方式，不另起服务器。

标准流程：HTML 控件 → JS 事件 → HTTP JSON → view.py → 业务 Python → JSON → JS 渲染。

HTML 不直接调用 Python。这里的“发消息”是浏览器 DOM 事件和 fetch HTTP 请求。

## 1. 明确功能契约

先列出每项功能的控件 id、HTTP 方法、URL、请求字段、成功响应、业务函数和错误表现。已有功能在原文件增量修改，避免重复注册。

- 读取设置：GET，返回当前保存的配置并回填控件。
- 保存设置：POST JSON，校验并持久化，返回保存后的实际配置。
- 执行长任务：返回启动状态，后台执行，再通过状态接口查询。

字段必须从控件到 JS、view 和业务参数完整映射；控件 id 可以不同于 JSON 字段，但映射必须明确。不要用 bool('false') 或静默默认值掩盖类型错误。

## 2. 接好工作台文件

1. web/pages/<page>.html：页面片段，设置稳定控件 id、状态提示区和按钮 type。
2. web/assets/js/pages/<page>.js：导出 mount/unmount；mount 绑定事件并 GET 初始化；提交时读取控件并 JSON.stringify；检查 response.ok 与 data.ok；成功后回填服务端数据；失败显示可读错误；finally 恢复按钮。
3. 页面使用 shared/page-scope.js 的 createPageScope，使用 scope.fetch、scope.setInterval；unmount 调用 scope.dispose，并清理额外监听器。
4. 新页面在 web/assets/js/app.js 的 pageTitles、pageModules 登记；顶层入口加到 web/index.html 的 data-page，子页面由 load(page) 进入。
5. src/view/<page>_view.py：from . import router，通过 @router.route 注册 GET/POST；handle(ctx) 解析并校验参数，调用业务函数，以 ctx.request.send_json 返回，最后 return True。
6. src/view/routes.py 导入新 view，否则装饰器不执行。无需在 server.py 的 legacy 分支重复实现。
7. 业务函数负责配置读取、持久化和执行；view 保持为接口适配层。使用已有存储模块，不把秘密值返回浏览器。

GET 的 ctx.body 为空；查询参数从 ctx.request.path 解析。POST 请求带 Content-Type: application/json。统一成功响应 {"ok": true, ...}，错误 {"ok": false, "error": "..."}。检查 server.py 当前错误映射；本仓库 POST 的 ValueError/KeyError 返回 400，RuntimeError 返回 409。

## 3. 验证闭环

- 对照 HTML id 与 JS selector、JS URL 与路由、请求字段与业务参数、响应字段与渲染代码。
- 对实际修改的 JS/Python 做语法检查；通过目标 view 的真实路由调用验证 GET、POST 和参数错误，不能只直接测业务函数。
- 可用服务中验证：打开页面自动回填 → 修改 → 保存 → 刷新后仍保留；模拟失败后提示可见且按钮恢复。
- 有执行按钮时验证启动、进度和完成；有轮询时切换页面确认请求停止。
- 验证不得覆盖用户现有配置或启动未授权任务；使用隔离配置或可恢复数据。运行环境不可用时明确未验证项，不能声称已跑通。

完成时提供实际调用链、涉及文件和验证结果。模板见 [references/settings-example.md](references/settings-example.md)。
