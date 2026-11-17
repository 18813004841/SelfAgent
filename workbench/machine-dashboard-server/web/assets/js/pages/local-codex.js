import { LOCAL_AGENT_ORIGIN } from "../shared/local-agent.js";
import { createPageScope } from "../shared/page-scope.js";
import { load } from "../app.js";
let scope;
const api = (path, options) => scope.fetch(path.startsWith("/api/local-codex/") ? LOCAL_AGENT_ORIGIN + path : path, options);
export async function mount() {
  scope = createPageScope();
  const input = document.getElementById("local-codex-url");
  const status = document.getElementById("local-codex-status");
  const save = document.getElementById("local-codex-save");
  const test = document.getElementById("local-codex-test");
  const processStatus = document.getElementById("local-codex-process-status");
  const pid = document.getElementById("local-codex-pid");
  const consoleState = document.getElementById("local-codex-console");
  const serverPid = document.getElementById("local-codex-server-pid");
  const processMsg = document.getElementById("local-codex-process-msg");
  const list = document.getElementById("local-codex-task-list");
  let tasks = [];
  const loadTasks = async () => { const d = await (await api("/api/local-codex/tasks")).json(); tasks = d.tasks || []; };
  const statusText = (task) => ({ completed: "执行完成", failed: "执行失败", cancelled: "已取消", timed_out: "执行超时", running: "执行中" }[task.status] || "尚未执行");
  function renderTasks() {
    list.replaceChildren();
    if (!tasks.length) { list.textContent = "暂无任务"; return; }
    tasks.forEach((task) => {
      const row = document.createElement("div");
      row.className = "card"; row.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin:8px 0";
      const open = document.createElement("button"); open.type = "button"; open.style.cssText = "flex:1;text-align:left;background:none;border:0";
      open.innerHTML = "<strong></strong><span class='muted'></span>";
      open.firstChild.textContent = task.name; open.lastChild.textContent = "  " + statusText(task);
      open.onclick = () => load("local-codex-task?id=" + encodeURIComponent(task.id));
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "删除";
      remove.onclick = async () => { if (!confirm("确认删除任务“" + task.name + "”？")) return; await api("/api/local-codex/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "delete", id: task.id }) }); await loadTasks(); renderTasks(); };
      row.append(open, remove); list.append(row);
    });
  }
  document.getElementById("local-codex-new").onclick = async () => {
    const name = window.prompt("任务名称", "Codex任务" + (tasks.length + 1));
    const cwd = window.prompt("工程工作区路径", "D:\\koa-client-code");
    if (!name || !name.trim() || !cwd || !cwd.trim()) return;
    const response = await api("/api/local-codex/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.trim(), cwd: cwd.trim() }) });
    const data = await response.json(); if (!response.ok || !data.ok) { status.textContent = data.error || "创建失败"; return; }
    await loadTasks(); renderTasks();
  };
  const show = (text, error = false) => { status.textContent = text; status.style.color = error ? "#b42318" : "#18753a"; };
  save.onclick = async () => { save.disabled = true; try { const r = await api("/api/local-codex/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ local_codex_url: input.value }) }); const d = await r.json(); if (!r.ok || !d.ok) throw Error(d.error || "保存失败"); input.value = d.config.local_codex_url; show("配置已保存"); } catch (e) { show("保存失败：" + e.message, true); } finally { save.disabled = false; } };
  test.onclick = async () => { test.disabled = true; show("正在测试连接…"); try { const r = await api("/api/local-codex/test", { method: "POST" }); const d = await r.json(); show(d.message, !d.reachable); } catch (e) { show("测试失败：" + e.message, true); } finally { test.disabled = false; } };
  try { const r = await api("/api/local-codex/config"); const d = await r.json(); if (!r.ok || !d.ok) throw Error(d.error || "加载失败"); input.value = d.config.local_codex_url; } catch (e) { show("加载失败：" + e.message, true); }
  async function refreshProcess() { try { const d = await (await api("/api/local-codex/status")).json(); processStatus.textContent = d.running ? "运行中" : "已停止"; processStatus.style.color = d.running ? "#18753a" : "#7b8492"; pid.textContent = d.pid || "-"; consoleState.textContent = d.console ? "已打开" : "未打开"; consoleState.style.color = d.console ? "#18753a" : "#7b8492"; serverPid.textContent = d.server_pid || "-"; } catch { processStatus.textContent = "状态未知"; } }
  document.getElementById("local-codex-start").onclick = async () => { processMsg.textContent = "正在启动..."; try { const d = await (await api("/api/local-codex/start", { method: "POST" })).json(); processMsg.textContent = d.ok ? "启动请求已发送" : (d.error || "启动失败"); await refreshProcess(); } catch (e) { processMsg.textContent = "启动失败：" + e.message; } };
  document.getElementById("local-codex-stop").onclick = async () => { processMsg.textContent = "正在停止..."; try { const d = await (await api("/api/local-codex/stop", { method: "POST" })).json(); processMsg.textContent = d.ok ? "已停止" : (d.error || "停止失败"); await refreshProcess(); } catch (e) { processMsg.textContent = "停止失败：" + e.message; } };
  await refreshProcess(); scope.setInterval(refreshProcess, 1500);
  await loadTasks(); renderTasks();
}
export function unmount() { scope?.dispose(); }
