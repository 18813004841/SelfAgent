import { createPageScope } from "../shared/page-scope.js";
import { showTip } from "../shared/tips.js";
let scope, pollTimer;
export async function mount(root) {
  scope = createPageScope();
  const form = root.querySelector("#project37-form");
  const preflight = root.querySelector("#project37-preflight");
  const save = root.querySelector("#project37-save");
  const execute = root.querySelector("#project37-execute");
  const log = root.querySelector(".project37-log");
  const resume = root.querySelector("#project37-continue");
  const push = root.querySelector("#project37-push");
  const conflictSection = root.querySelector("#project37-conflicts");
  const conflictList = root.querySelector("#project37-conflict-list");
  let currentTask;
  const fields = [...form.querySelectorAll("input[name]")];
  const status = root.querySelector("#project37-status");
  const apply = settings => fields.forEach(field => { field.value = settings[field.name] ?? ""; });
  const readResponse = async response => {
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || `请求失败（${response.status}）`);
    return data;
  };
  fields.forEach(field => { field.disabled = true; });
  save.disabled = true;
  preflight.disabled = true;
  try {
    const data = await readResponse(await scope.fetch("/api/server-maintenance/project37/settings"));
    apply(data.settings);
  } catch (error) {
    showTip(`参数读取失败：${error.message}`, { type: "error" });
  } finally {
    fields.forEach(field => { field.disabled = false; });
    save.disabled = false;
    preflight.disabled = false;
  }
  save.onclick = async () => {
    save.disabled = true;
    const submitted = Object.fromEntries(new FormData(form));
    try {
      const data = await readResponse(await scope.fetch("/api/server-maintenance/project37/settings", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(submitted)}));
      fields.forEach(field => { if (field.value === submitted[field.name]) field.value = data.settings[field.name]; });
      showTip("参数保存成功", { type: "success" });
    } catch (error) {
      showTip(`参数保存失败：${error.message}`, { type: "error" });
    } finally { save.disabled = false; }
  };
  preflight.onclick = async () => {
    if (!form.reportValidity()) return;
    preflight.disabled = true;
    log.textContent = "正在检查仓库和远端引用…";
    try {
      const data = await readResponse(await scope.fetch("/api/server-maintenance/project37/preflight", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(Object.fromEntries(new FormData(form)))}));
      log.textContent = `预检通过\n37工程：${data.result.project_root}\n37data：${data.result.data_root}\nFBS：${data.result.fbs_path}`;
    } catch (error) { log.textContent = `预检失败：${error.message}`; }
    finally { preflight.disabled = false; }
  };
  let polling = false;
  const render = task => {
    if (!task) return;
    currentTask = task;
    const active = ["queued", "running", "pushing"].includes(task.status);
    const waiting = task.can_resume;
    execute.disabled = active || task.status === "paused";
    resume.hidden = !waiting;
    push.hidden = !task.can_push;
    conflictSection.hidden = !(task.conflicts || []).length;
    conflictList.replaceChildren(...(task.conflicts || []).map(path => { const item = document.createElement("li"); item.textContent = path; return item; }));
    status.textContent = ({queued:"等待执行", running:"执行中", completed:"执行完成", failed:"执行失败", paused:"等待管理员处理冲突", pushing:"正在推送"})[task.status] || task.status;
    log.textContent = (task.events || []).map(event => `[${event.time}] ${event.message}`).join("\n") || status.textContent;
    if (!active && pollTimer) { clearInterval(pollTimer); pollTimer = undefined; }
  };
  const watch = task => {
    render(task);
    if (!task || !["queued", "running", "pushing"].includes(task.status) || pollTimer) return;
    pollTimer = scope.setInterval(async () => {
      if (polling) return;
      polling = true;
      try { render((await readResponse(await scope.fetch(`/api/server-maintenance/project37/tasks/${encodeURIComponent(task.id)}`))).task); }
      catch (error) { status.textContent = `查询任务失败：${error.message}`; }
      finally { polling = false; }
    }, 1500);
  };
  execute.onclick = async () => {
    if (!form.reportValidity()) return;
    if (!window.confirm("将清理两个仓库的本地修改和未跟踪文件，并丢弃目标分支上的本地未推送提交。操作不可撤销，确定执行？")) return;
    execute.disabled = true;
    try {
      const data = await readResponse(await scope.fetch("/api/server-maintenance/project37/tasks", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(Object.fromEntries(new FormData(form)))}));
      watch(data.task);
    } catch (error) { execute.disabled = false; showTip(`启动失败：${error.message}`, {type:"error"}); }
  };
  async function taskAction(button, url) {
    if (!currentTask || button.disabled) return;
    button.disabled = true;
    try {
      const data = await readResponse(await scope.fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({task_id:currentTask.id})}));
      watch(data.task);
    } catch (error) { showTip(error.message, {type:"error"}); }
    finally { button.disabled = false; }
  }
  resume.onclick = () => taskAction(resume, "/api/server-maintenance/project37/continue");
  push.onclick = () => {
    if (window.confirm("确认将本次成功任务的新分支推送到 origin？")) taskAction(push, "/api/server-maintenance/project37/push");
  };
  try { watch((await readResponse(await scope.fetch("/api/server-maintenance/project37/tasks/latest"))).task); }
  catch (error) { status.textContent = `读取任务失败：${error.message}`; }
}
export function unmount() { if (pollTimer) clearInterval(pollTimer); pollTimer = undefined; scope?.dispose(); }
