import { createPageScope } from "../shared/page-scope.js";
import { localApi, LOCAL_AGENT_ORIGIN } from "../shared/local-agent.js";
let scope;
const api = (...args) => scope.fetch(...args);
const interval = (...args) => scope.setInterval(...args);
export async function mount() {
  scope = createPageScope();
  const ip = document.getElementById("central-server-ips"), conn = document.getElementById("central-client-connection-status");
  const ss = document.getElementById("central-server-status"), cs = document.getElementById("central-client-status");
  const sm = document.getElementById("central-server-msg"), cm = document.getElementById("central-client-msg");
  const download = document.getElementById("central-client-download"), update = document.getElementById("central-client-update");
  const serverInput = document.getElementById("central-client-server");
  // The central server is reached through the same host the user opened in
  // the browser.  A previously saved LAN address can belong to another
  // machine or network, so it must not override the current page origin.
  serverInput.value = `${location.protocol}//${location.hostname}:18765`;
  async function refresh() {
    try {
      const server = await api("/api/central-server/status", { cache: "no-store" }).then(r => r.json());
      ss.textContent = server.running ? "运行中" : "已停止"; ss.style.color = server.running ? "green" : "#888";
      document.getElementById("central-server-port").textContent = server.port || 18765;
      const client = await localApi("/api/central-client/status");
      cs.textContent = client.running ? "运行中" : "已停止"; cs.style.color = client.running ? "green" : "#888";
      const files = document.getElementById("central-client-files"); files.textContent = client.client_entry_exists ? "已找到本机客户端文件" : "本机未找到客户端文件"; files.style.color = client.client_entry_exists ? "green" : "#c77";
      try {
        const releaseResponse = await api("/api/central-client/version", { cache: "no-store" });
        const release = await releaseResponse.json();
        if (!releaseResponse.ok || !release.ok) throw Error(release.error || "无法读取客户端版本");
        const hasUpdate = client.client_entry_exists && release.version !== client.version;
        download.textContent = hasUpdate ? "更新客户端" : (client.client_entry_exists ? "重新安装客户端" : "下载客户端");
        update.textContent = hasUpdate ? `当前 ${client.version || "未记录"}，可更新到 ${release.version}` : (client.version ? `版本 ${client.version}` : "");
        update.style.color = hasUpdate ? "#b45309" : "";
      } catch {
        download.textContent = client.client_entry_exists ? "重新安装客户端" : "下载客户端";
        update.textContent = client.version ? `版本 ${client.version}` : "版本检查暂不可用";
        update.style.color = "#888";
      }
      document.getElementById("central-client-dir").textContent = client.client_dir || "";
      conn.textContent = server.running ? "已连接" : "未连接";
    } catch (error) { cs.textContent = "本机服务不可用"; cs.style.color = "#c77"; cm.textContent = error.message; }
  }
  async function refreshIps() { try { const d = await api("/api/central-server/connections", { cache: "no-store" }).then(r => r.json()); ip.textContent = d.ips?.length ? d.ips.join("、") : "暂无连接"; } catch { ip.textContent = "暂无连接"; } }
  await refresh(); await refreshIps(); interval(() => { refresh(); refreshIps(); }, 3000);
  document.getElementById("central-server-start").onclick = async () => { sm.textContent = "正在启动..."; await api("/api/central-server/start", { method: "POST" }); await refresh(); };
  document.getElementById("central-server-stop").onclick = async () => { sm.textContent = "正在关闭..."; await api("/api/central-server/stop", { method: "POST" }); await refresh(); };
  document.getElementById("central-server-cleanup").onclick = async () => { const d = await api("/api/central-server/cleanup", { method: "POST" }).then(r => r.json()); sm.textContent = "已清理端口 " + d.port; await refresh(); };
  document.getElementById("central-client-start").onclick = async () => { cm.textContent = "正在本机启动..."; try { localStorage.setItem("central-client-server", serverInput.value.trim()); await localApi("/api/central-client/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ central_server_url: serverInput.value.trim() }) }); cm.textContent = "已向本机发送启动请求"; } catch (e) { cm.textContent = e.message; } await refresh(); };
  document.getElementById("central-client-stop").onclick = async () => { try { await localApi("/api/central-client/stop", { method: "POST" }); cm.textContent = "已关闭本机客户端"; } catch (e) { cm.textContent = e.message; } await refresh(); };
  document.getElementById("central-client-open").onclick = async () => { try { await localApi("/api/settings/storage/open", { method: "POST" }); cm.textContent = "已打开本机保存目录"; } catch (e) { cm.textContent = e.message; } };
  document.getElementById("central-client-download").onclick = async e => { e.preventDefault(); cm.textContent = "正在下载并安装到本机..."; try { const response = await api("/api/central-client/download"); const bytes = await response.arrayBuffer(); const installed = await fetch(LOCAL_AGENT_ORIGIN + "/api/central-client/install", { method: "POST", headers: { "Content-Type": "application/zip" }, body: bytes }); const data = await installed.json(); if (!installed.ok || !data.ok) throw Error(data.error || "安装失败"); cm.textContent = "已安装到本机：" + data.client_dir; await refresh(); } catch (e) { cm.textContent = e.message; } };
}
export function unmount() { scope?.dispose(); }
