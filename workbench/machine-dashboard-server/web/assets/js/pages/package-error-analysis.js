const read = async () => { try { const r = await fetch("/api/package-error-analysis/tasks"); const d = await r.json(); return d.tasks || []; } catch { return []; } };
export async function mount() {
  const add = document.querySelector("#create-analysis-task"); const list = document.querySelector("#analysis-task-list"); const empty = document.querySelector("#analysis-empty");
  const render = async () => { const items = await read(); empty.hidden = items.length > 0; list.innerHTML = items.map((t, i) => `<button class="analysis-task-card" data-task-id="${t.id}"><span class="task-symbol">!</span><span class="task-card-main"><strong>打包报错分析 ${items.length - i}</strong><small>创建于 ${t.createdAt || ""}</small></span><span class="analysis-status ${t.status === "completed" ? "done" : ""}">${t.status}</span><span class="module-arrow">→</span></button>`).join(""); list.querySelectorAll("[data-task-id]").forEach(b => b.onclick = () => { window.__analysisTaskId = b.dataset.taskId; window.dispatchEvent(new CustomEvent("workbench:navigate", {detail:"package-error-analysis-task"})); }); };
  add.onclick = () => { window.__analysisTaskId = ""; window.dispatchEvent(new CustomEvent("workbench:navigate", {detail:"package-error-analysis-task"})); };
  await render();
}
export function unmount() {}
