import { load } from "../app.js";
import { createPageScope } from "../shared/page-scope.js";
let scope;
const fetch = (...args) => scope.fetch(...args);
const setInterval = (...args) => scope.setInterval(...args);
async function initCentralServer() {
  const ipBox = document.getElementById("central-server-ips"),
    connStatus = document.getElementById("central-client-connection-status");
  async function refreshIps() {
    try {
      const d = await fetch("/api/central-server/connections", {
        cache: "no-store",
      }).then((r) => r.json());
      const connected = !!(d.ips && d.ips.length);
      ipBox.textContent = connected ? d.ips.join("、") : "暂无连接";
      ipBox.style.color = connected ? "green" : "#888";
      if (connStatus) {
        connStatus.textContent = connected ? "已连接" : "未连接";
        connStatus.style.color = connected ? "green" : "#888";
      }
    } catch (e) {
      ipBox.textContent = "暂无连接";
      if (connStatus) {
        connStatus.textContent = "连接检查失败";
        connStatus.style.color = "#c77";
      }
    }
  }
  await refreshIps();
  const ss = document.getElementById("central-server-status"),
    cs = document.getElementById("central-client-status"),
    sm = document.getElementById("central-server-msg"),
    cm = document.getElementById("central-client-msg");
  async function refresh() {
    try {
      const [a, b] = await Promise.all([
        fetch("/api/central-server/status", { cache: "no-store" }).then((r) =>
          r.json(),
        ),
        fetch("/api/central-client/status", { cache: "no-store" }).then((r) =>
          r.json(),
        ),
      ]);
      ss.textContent = a.running ? "运行中" : "已停止";
      document.getElementById("central-server-port").textContent =
        a.port || 18765;
      cs.textContent = b.running ? "运行中" : "已停止";
      ss.style.color = a.running ? "green" : "#888";
      cs.style.color = b.running ? "green" : "#888";
      if (!b.running) {
        ipBox.textContent = "暂无连接";
        ipBox.style.color = "#888";
        if (connStatus) {
          connStatus.textContent = "未连接";
          connStatus.style.color = "#888";
        }
      }
      const f = document.getElementById("central-client-files");
      f.textContent = b.client_entry_exists
        ? "已找到客户端文件"
        : "未找到客户端文件";
      f.style.color = b.client_entry_exists ? "green" : "#c77";
      document.getElementById("central-client-dir").textContent =
        b.client_dir || "";
    } catch (e) {
      ss.textContent = cs.textContent = "状态未知";
    }
  }
  await refresh();
  if (window.__centralTimer) clearInterval(window.__centralTimer);
  window.__centralTimer = setInterval(() => {
    refresh();
    refreshIps();
  }, 3000);
  document.getElementById("central-server-start").onclick = async () => {
    sm.textContent = "正在启动...";
    await fetch("/api/central-server/start", { method: "POST" });
    await refresh();
    sm.textContent = "启动请求已发送";
  };
  document.getElementById("central-server-stop").onclick = async () => {
    sm.textContent = "正在关闭...";
    await fetch("/api/central-server/stop", { method: "POST" });
    await refresh();
    sm.textContent = "关闭请求已发送";
  };
  document.getElementById("central-server-cleanup").onclick = async () => {
    sm.textContent = "正在清理端口进程...";
    const d = await fetch("/api/central-server/cleanup", {
      method: "POST",
    }).then((r) => r.json());
    sm.textContent =
      "已清理端口 " + d.port + "，结束进程 " + (d.killed || []).join(", ");
    await refresh();
  };
  document.getElementById("central-client-start").onclick = async () => {
    cm.textContent = "正在启动...";
    await fetch("/api/central-client/start", { method: "POST" });
    await refresh();
    cm.textContent = "启动请求已发送";
  };
  document.getElementById("central-client-stop").onclick = async () => {
    cm.textContent = "正在关闭...";
    await fetch("/api/central-client/stop", { method: "POST" });
    await refresh();
    cm.textContent = "关闭请求已发送";
  };
  document.getElementById("central-client-open").onclick = async () => {
    const r = await fetch("/api/settings/storage/open");
    const d = await r.json();
    cm.textContent = d.ok ? "已打开本地保存目录" : "打开失败";
  };
}
export async function mount() {
  scope = createPageScope();
  await initCentralServer();
}
export function unmount() {
  scope?.dispose();
}
