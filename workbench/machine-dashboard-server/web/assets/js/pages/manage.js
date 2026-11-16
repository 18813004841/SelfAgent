import { load } from "../app.js";
import { createPageScope } from "../shared/page-scope.js";
let scope;
const fetch = (...args) => scope.fetch(...args);
const setInterval = (...args) => scope.setInterval(...args);
async function initManage() {
  const tools = document.getElementById("manage-tools"),
    machines = document.getElementById("manage-machines"),
    schedules = document.getElementById("manage-schedules"),
    msg = document.getElementById("manage-msg"),
    status = document.getElementById("central-server-status"),
    centerMsg = document.getElementById("central-server-msg");
  if (window.__centralTimer) clearInterval(window.__centralTimer);
  async function refreshCenter() {
    try {
      const d = await fetch("/api/central-server/status", {
        cache: "no-store",
      }).then((r) => r.json());
      if (status) {
        status.textContent = d.running ? "运行中" : "已停止";
        status.style.color = d.running ? "green" : "#888";
      }
    } catch (e) {
      if (status) {
        status.textContent = "状态未知";
        status.style.color = "#c77";
      }
    }
  }
  try {
    const [tr, mr, sr] = await Promise.all([
      fetch("/api/tools"),
      fetch("/api/machines"),
      fetch("/api/schedules"),
    ]);
    const [td, md, sd] = await Promise.all([tr.json(), mr.json(), sr.json()]);
    machines.textContent = md.machines.length + " 台";
    tools.textContent = td.tools.length + " 个";
    schedules.textContent = sd.schedules.length + " 个";
    msg.textContent = "数据已更新 · " + new Date().toLocaleTimeString();
  } catch (e) {
    msg.textContent = "加载失败：" + e.message;
  }
  await refreshCenter();
  async function refreshClient() {
    try {
      const d = await fetch("/api/central-client/status", {
        cache: "no-store",
      }).then((r) => r.json());
      const s = document.getElementById("central-client-status");
      if (s) {
        s.textContent = d.running ? "运行中" : "已停止";
        s.style.color = d.running ? "green" : "#888";
      }
    } catch (e) {
      const clientStatus = document.getElementById("central-client-status");
      if (clientStatus) clientStatus.textContent = "状态未知";
    }
  }
  await refreshClient();
  const agentStatus = document.getElementById("openai-agent-status"),
    agentPort = document.getElementById("openai-agent-port"),
    agentMsg = document.getElementById("openai-agent-msg");
  async function refreshAgent() {
    try {
      const d = await fetch("/api/openai-agent/status", {
        cache: "no-store",
      }).then((r) => r.json());
      if (agentStatus) {
        agentStatus.textContent = d.running ? "运行中" : "已停止";
        agentStatus.style.color = d.running ? "green" : "#888";
      }
      if (agentPort) agentPort.textContent = d.port || 8765;
    } catch (e) {
      if (agentStatus) {
        agentStatus.textContent = "状态未知";
        agentStatus.style.color = "#c77";
      }
    }
  }
  await refreshAgent();
  const agentStart = document.getElementById("openai-agent-start");
  if (agentStart) agentStart.onclick = async () => {
    agentMsg.textContent = "正在启动...";
    const r = await fetch("/api/openai-agent/start", { method: "POST" });
    const d = await r.json();
    agentMsg.textContent = d.ok
      ? "启动请求已发送"
      : "启动失败：" + (d.error || "");
    await refreshAgent();
  };
  const agentStop = document.getElementById("openai-agent-stop");
  if (agentStop) agentStop.onclick = async () => {
    agentMsg.textContent = "正在停止...";
    const r = await fetch("/api/openai-agent/stop", { method: "POST" });
    const d = await r.json();
    agentMsg.textContent = d.ok
      ? "停止请求已发送"
      : "停止失败：" + (d.error || "");
    await refreshAgent();
  };
  window.__centralTimer = setInterval(() => {
    refreshCenter();
    refreshClient();
    refreshAgent();
  }, 3000);
  const centerStart = document.getElementById("central-server-start");
  if (centerStart) centerStart.onclick = async () => {
    centerMsg.textContent = "正在启动...";
    await fetch("/api/central-server/start", { method: "POST" });
    await refreshCenter();
    centerMsg.textContent = "启动请求已发送";
  };
  const centerStop = document.getElementById("central-server-stop");
  if (centerStop) centerStop.onclick = async () => {
    centerMsg.textContent = "正在关闭...";
    await fetch("/api/central-server/stop", { method: "POST" });
    await refreshCenter();
    centerMsg.textContent = "关闭请求已发送";
  };
  const clientMsg = document.getElementById("central-client-msg");
  const clientStart = document.getElementById("central-client-start");
  if (clientStart) clientStart.onclick = async () => {
    clientMsg.textContent = "正在启动...";
    await fetch("/api/central-client/start", { method: "POST" });
    await refreshClient();
    clientMsg.textContent = "启动请求已发送";
  };
  const clientStop = document.getElementById("central-client-stop");
  if (clientStop) clientStop.onclick = async () => {
    clientMsg.textContent = "正在关闭...";
    await fetch("/api/central-client/stop", { method: "POST" });
    await refreshClient();
    clientMsg.textContent = "关闭请求已发送";
  };
}
export async function mount() {
  scope = createPageScope();
  await initManage();
}
export function unmount() {
  scope?.dispose();
}
