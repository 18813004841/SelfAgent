# macOS 安装说明

从浏览器下载并解压后，macOS 可能提示脚本来自互联网或没有执行权限。这是 macOS Gatekeeper 对下载文件添加的隔离标记，Windows 无法在打包时移除。

在 Terminal 中执行以下命令（把路径替换为实际解压目录）：

```bash
cd ~/Downloads/machine-dashboard-client
xattr -dr com.apple.quarantine .
chmod +x start-local-agent.command start-local-agent.sh
./start-local-agent.command
```

之后可以直接双击 `start-local-agent.command` 启动。首次运行需要安装 Python 3.11 或更新版本。
