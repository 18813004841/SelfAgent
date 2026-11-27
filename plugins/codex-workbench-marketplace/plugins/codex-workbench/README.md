# SelfAgent Codex 插件

独立的本地 MCP 插件，主界面显示当前版本并提供检查和安装更新。插件不连接工作台，也不需要登录。`server.js` 是 MCP 入口，`index.html` 是主界面，后续独立功能放在 `features/`，由入口显式注册。

## 安装和更新

在仓库根目录执行 `codex plugin marketplace add ./plugins/codex-workbench-marketplace`，重启 Codex，在 SelfAgent Plugins 中安装「SelfAgent 插件」。也可以调用 `open_workbench` 打开主界面；名称保留用于兼容已有调用。全局入口是否展示取决于宿主支持。

插件启动时及点击按钮时读取已注册的 `selfagent-workbench` 本地插件源中的版本。请先将该源目录更新到期望版本；本地源不会自动拉取代码。发现较新版本后，点击安装将调用 `codex plugin add codex-workbench@selfagent-workbench --json`，完成后重启 Codex。需要 Node.js 和 Codex CLI 在 PATH 中可用。源未配置、CLI 不可用或安装失败时界面会显示错误；若缓存被占用，可退出 Codex 后在终端重试该命令。旧名称仅作为安装标识保留。

运行 `node --test tests/integration.test.js` 验证版本比较、更新调用及 MCP 入口。测试使用临时插件源，不修改用户配置或安装插件。

主页的“重启 Codex”按钮仅支持 Windows 应用包安装：后台助手关闭 Codex 并通过 Windows 应用入口重新启动。重启会中断正在运行的任务；如果没有重新打开，请查看 `%LOCALAPPDATA%/SelfAgent/codex-plugin/restart.log` 并手动启动。启动助手成功不等于重启已完成。

代码辅助分析可绑定工程并以只读模式启动独立 Codex 会话，支持发送消息和查看流式事件。监听执行和清理尚未接入；真实 Codex 会话与 Unity 联调尚未验证。

在代码辅助分析页面点击“绑定工程”可打开 Windows 文件夹选择窗口，取消选择不会更改绑定；也可手动输入路径后点击“使用输入的路径”。
