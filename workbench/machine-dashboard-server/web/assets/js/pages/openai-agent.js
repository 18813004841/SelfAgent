import { load } from "../app.js";
import { createPageScope } from "../shared/page-scope.js";
let scope;
const fetch = (...args) => scope.fetch(...args);
const setInterval = (...args) => scope.setInterval(...args);
async function refreshOpenAiAgentStatus() {
  const s = document.getElementById("agent-page-status"),
    p = document.getElementById("agent-page-port");
  if (!s) return;
  try {
    const d = await fetch("/api/openai-agent/status", {
      cache: "no-store",
    }).then((r) => r.json());
    s.textContent = d.running ? "运行中" : "已停止";
    s.style.color = d.running ? "green" : "#888";
    p.textContent = d.port || 8765;
  } catch (e) {
    s.textContent = "状态未知";
    s.style.color = "#c77";
  }
}

async function cleanupOpenAiAgent() {
  const m = document.getElementById("openai-agent-msg");
  m.textContent = "正在清理端口进程...";
  try {
    const d = await fetch("/api/openai-agent/cleanup", { method: "POST" }).then(
      (r) => r.json(),
    );
    m.textContent =
      "已清理端口 " + d.port + "，结束进程 " + (d.killed || []).join(", ");
    await refreshOpenAiAgentStatus();
  } catch (e) {
    m.textContent = "清理失败：" + e.message;
  }
}

async function startOpenAiAgent() {
  const m = document.getElementById("openai-agent-msg");
  m.textContent = "正在启动...";
  try {
    const r = await fetch("/api/openai-agent/start", { method: "POST" }),
      d = await r.json();
    m.textContent = d.ok
      ? "启动请求已发送：PID " + (d.pid || "")
      : "启动失败：" + (d.error || "未知错误");
  } catch (e) {
    m.textContent = "启动请求失败：" + e.message;
  }
  await refreshOpenAiAgentStatus();
}

async function stopOpenAiAgent() {
  const m = document.getElementById("openai-agent-msg");
  m.textContent = "正在停止...";
  try {
    const r = await fetch("/api/openai-agent/stop", { method: "POST" }),
      d = await r.json();
    m.textContent = d.ok
      ? "停止请求已发送"
      : "停止失败：" + (d.error || "未知错误");
  } catch (e) {
    m.textContent = "停止请求失败：" + e.message;
  }
  await refreshOpenAiAgentStatus();
}

async function initOpenAiAgent() {
  await refreshOpenAiAgentStatus();
  setInterval(refreshOpenAiAgentStatus, 1000);
  document.getElementById("agent-chat-send").onclick = async () => {
    const input = document.getElementById("agent-chat-input"),
      status = document.getElementById("agent-chat-status"),
      answer = document.getElementById("agent-chat-answer");
    if (!input.value.trim()) return;
    const startedAt = performance.now();
    status.textContent = "请求中...";
    try {
      const d = await fetch("/api/openai-agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: input.value,
          model: document.getElementById("agent-chat-model").value,
        }),
      }).then((r) => r.json());
      const elapsed = ((performance.now() - startedAt) / 1000).toFixed(2);
      if (!d.ok) throw Error(d.error);
      answer.textContent = d.answer;
      status.textContent = "完成 · 耗时 " + elapsed + " 秒";
    } catch (e) {
      const elapsed = ((performance.now() - startedAt) / 1000).toFixed(2);
      status.textContent = "请求失败 · 耗时 " + elapsed + " 秒：" + e.message;
    }
  };
}
export async function mount() {
  scope = createPageScope();
  document.querySelector("#agent-start").onclick = startOpenAiAgent;
  document.querySelector("#agent-stop").onclick = stopOpenAiAgent;
  document.querySelector("#agent-cleanup").onclick = cleanupOpenAiAgent;
  await initOpenAiAgent();
}
export function unmount() {
  scope?.dispose();
}
