# Codex KOA工作台插件

这是一个独立的本地 MCP 插件，提供登录、工作台机器概览、定时任务列表、服务器设置和版本检查。服务器地址默认为 `http://10.0.76.228:18888/`，保存在 `%LOCALAPPDATA%/LocalWorkbench/codex-plugin/settings.json`（其他系统使用 XDG 配置目录）。连接测试调用工作台 `/api/auth/session`。登录复用工作台 HTTP API，会话只保存在插件进程内；不保存密码或会话，重启插件或切换服务器后需要重新登录。HTTP 连接不加密，界面会提示。机器概览是工作台服务器所在机器的数据。任务页面当前无业务内容，管理入口跳转原工作台。

插件通过固定的 `selfagent-workbench` 本地插件源检查新版本；点击更新时调用 `codex plugin add codex-workbench@selfagent-workbench`，成功后需重启 Codex。如果插件缓存被占用，请退出 Codex 后在终端重试。打开工作台会请求系统默认浏览器，失败时显示可复制的地址。Node.js 和 Codex CLI 需在 PATH 中可用。

## 安装和使用

在仓库根目录运行：

```powershell
codex plugin marketplace add ./plugins/codex-workbench-marketplace
```

重启桌面应用，在插件目录选择 SelfAgent Plugins 并安装「KOA工作台」，然后开启新对话。也可尝试调用 `open_workbench`。修改后需更新或重新安装插件，重启桌面应用以加载缓存副本。

工具声明了 MCP App 全局入口。OpenAI 文档将该入口描述为 ChatGPT 侧边栏功能；Codex 桌面端是否显示入口取决于宿主版本及其支持，尚未确认。安装成功不代表侧边栏按钮已出现。若没有按钮，本插件无法强制添加宿主导航项。

卸载插件后可通过 `codex plugin marketplace remove selfagent-workbench` 移除源。

## 验证

运行 `node --test tests/integration.test.js`，验证登录、会话失效、机器概览、定时任务读取及服务器地址切换。测试使用临时目录和本地模拟服务，不修改用户配置。
