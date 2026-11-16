import { createPageScope } from "../shared/page-scope.js";
let scope;
const api = (...args) => scope.fetch(...args);
const label = (status) => ({ completed: "执行完成", failed: "执行失败", running: "执行中" }[status] || "尚未执行");
function formatEvents(events) {
  const sections = []; const diagnostics = [];
  (events || []).forEach((event) => {
    const item = event.item || {};
    const text = item.text || event.text || "";
    if (item.type === "agent_message" && text) sections.push({ title: "Codex 回复", body: text });
    else if (item.type === "command_execution") sections.push({ title: "命令（" + (item.status === "completed" ? "完成" : "执行中") + "）", body: [item.command || "", String(item.aggregated_output || "").trim()].filter(Boolean).join("\n") });
    else if (event.message || /ERROR/i.test(text)) diagnostics.push(event.message || text);
  });
  if (diagnostics.length) sections.push({ title: "诊断日志（" + diagnostics.length + "）", body: diagnostics.join("\n\n") });
  return sections;
}
function addSection(parent, title, body, result) {
  const details = document.createElement("details"); details.style.margin = "8px 0 8px 24px";
  const summary = document.createElement("summary");
  summary.style.whiteSpace = "normal";
  summary.style.overflowWrap = "anywhere";
  summary.style.maxWidth = "100%";
  summary.style.marginLeft = "0";
  // 悬挂缩进：首行保留箭头位置，摘要换行内容与标题文字起点对齐。
  summary.style.paddingLeft = "20px";
  summary.style.textIndent = "-20px";
  summary.style.lineHeight = "1.6";
  summary.style.padding = "4px 0 4px 20px";
  const summaryText = title + (result ? " · 最终结果：" + result.slice(0, 2000) : " · " + String(body).slice(0, 200));
  const escape = (value) => value.replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  summary.innerHTML = escape(summaryText).replace(/(^|最终结果：)(#{1,6})\s+([^\n]+)/gm, "$1<strong>$3</strong>").replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>").replace(/(^|\n)\s*([-*]|\d+\.)\s+/g, "$1• ").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\n/g, "<br>");
  const pre = document.createElement("pre"); pre.className = "task-log"; pre.textContent = body;
  const content = document.createElement("div"); content.style.whiteSpace = "pre-wrap"; content.style.padding = "10px 14px 10px 20px"; content.style.marginLeft = "0";
  String(body).replace(/\r\n/g, "\n").split("\n").forEach((line) => {
    const row = document.createElement("div"); row.textContent = line || "\u00a0";
    if (/^#{1,3}\s/.test(line)) { row.textContent = line.replace(/^#{1,3}\s*/, ""); row.style.fontWeight = "700"; row.style.marginTop = "8px"; }
    else if (/^\s*(?:[-*]|\d+\.)\s+/.test(line)) { row.textContent = "• " + line.replace(/^\s*(?:[-*]|\d+\.)\s+/, ""); row.style.paddingLeft = "12px"; }
    content.append(row);
  });
  details.append(summary, title === "Codex" ? content : pre); parent.append(details);
}
function finalReply(messages) {
  const reply = [...(messages || [])].reverse().find((message) => message.role === "assistant");
  if (!reply) return "";
  const sections = String(reply.content).split(/(?:^|\n)Codex 回复\s*\n/);
  const last = sections[sections.length - 1];
  return last.replace(/^Codex：?\s*/i, "").split(/\n诊断日志|\n命令（/)[0].trim();
}
export async function mount(content, params) {
  scope = createPageScope();
  const id = params.get("id");
  const title = document.getElementById("codex-task-title"), prompt = document.getElementById("codex-task-prompt"), status = document.getElementById("codex-task-status"), log = document.getElementById("codex-task-log"), submit = document.getElementById("codex-task-submit"), workspace = document.getElementById("codex-task-workspace");
  const skills = document.getElementById("codex-task-skills");
  const extra = document.getElementById("codex-task-extra-rules");
  const saveSettings = document.getElementById("codex-task-save-settings");
  const settingsStatus = document.getElementById("codex-task-settings-status");
  const skillMenu = document.getElementById("codex-task-skill-menu");
  const skillPaths = () => [...skills.querySelectorAll("input")].map((input) => input.value.trim()).filter(Boolean);
  function renderSkills(paths) {
    skills.querySelectorAll(".skill-row").forEach((row) => row.remove());
    (paths.length ? paths : [""]).forEach((path) => {
      const row = document.createElement("div"); row.className = "skill-row"; row.style.cssText = "display:flex;gap:8px;margin:6px 0";
      const input = document.createElement("input"); input.value = path; input.style.flex = "1 1 auto"; input.style.minWidth = "0"; input.placeholder = "Skill 目录或 SKILL.md 路径";
      input.onchange = persistSkillConfig;
      const choose = document.createElement("button"); choose.type = "button"; choose.textContent = "选择目录";
      choose.onclick = async () => {
        const response = await api("/api/scheduler-tasks/code-review/choose", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ current_path: document.getElementById("codex-task-workspace").value.trim() || input.value.trim() }) });
        const data = await response.json();
        if (!response.ok || !data.ok) throw Error(data.error || "目录选择失败");
        if (data.project_path) { input.value = data.project_path; await persistSkillConfig(); }
      };
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "删除";
      remove.onclick = async () => { row.remove(); if (!skills.querySelector(".skill-row")) renderSkills([""]); await persistSkillConfig(); };
      row.append(input, choose, remove); skills.append(row);
    });
  }
  document.getElementById("codex-task-add-skill").onclick = async () => { renderSkills([...skillPaths(), ""]); await persistSkillConfig(); };
  let selectedSkillPaths = [];
  prompt.oninput = () => {
    const match = prompt.value.match(/@([^\s@]*)$/);
    if (!match) { skillMenu.hidden = true; return; }
    const query = match[1].toLowerCase(); skillMenu.replaceChildren();
    skillPaths().filter((path) => path.toLowerCase().includes(query)).forEach((path) => {
      const option = document.createElement("button"); option.type = "button"; option.textContent = path; option.style.cssText = "display:block;width:100%;padding:8px;text-align:left;border:0;background:white;cursor:pointer";
      option.onclick = () => { prompt.value = prompt.value.slice(0, prompt.value.length - match[0].length) + "@" + path + " "; selectedSkillPaths = [...new Set([...selectedSkillPaths, path])]; skillMenu.hidden = true; prompt.focus(); };
      skillMenu.append(option);
    });
    skillMenu.hidden = skillMenu.children.length === 0;
  };
  const load = async () => ((await (await api("/api/local-codex/tasks")).json()).tasks || []).find((item) => item.id === id);
  const save = (item) => api("/api/local-codex/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "update", id, ...item }) });
  async function persistSkillConfig() {
    const item = await load();
    if (!item) throw Error("任务不存在");
    if (item.status === "running") throw Error("任务执行中，请完成后保存设置");
    const response = await save({ cwd: workspace.value.trim(), status: item.status, prompt: item.prompt || "", messages: item.messages || [], log: item.log || "", skill_paths: skillPaths(), allow_extra_rules: extra.checked });
    const data = await response.json();
    if (!response.ok || !data.ok) throw Error(data.error || "保存失败");
  }
  saveSettings.onclick = async () => {
    saveSettings.disabled = true; settingsStatus.textContent = "正在保存…";
    try { await persistSkillConfig(); settingsStatus.textContent = "设置已保存"; settingsStatus.style.color = "#18753a"; }
    catch (error) { settingsStatus.textContent = "保存失败：" + error.message; settingsStatus.style.color = "#b42318"; }
    finally { saveSettings.disabled = false; }
  };
  extra.onchange = persistSkillConfig;
  const render = async () => {
    const item = await load(); log.replaceChildren();
    if (!item) { title.textContent = "任务不存在"; submit.disabled = true; return null; }
    title.textContent = item.name; workspace.value = item.cwd || ""; renderSkills(item.skill_paths || []); extra.checked = Boolean(item.allow_extra_rules); status.textContent = label(item.status);
    submit.disabled = item.status === "running";
    submit.textContent = item.status === "running" ? "执行中…" : "提交任务";
    (item.messages || []).forEach((message) => addSection(log, message.role === "user" ? "你" : "Codex", message.content, message.role === "assistant" ? finalReply([message]) : ""));
    return item;
  };
  workspace.onchange = async () => { const item = await load(); if (item) await save({ cwd: workspace.value.trim(), status: item.status || "idle", prompt: item.prompt || "", messages: item.messages || [], log: item.log || "", skill_paths: skillPaths(), allow_extra_rules: extra.checked }); };
  submit.onclick = async () => {
    const item = await load(); if (!item) return;
    const text = prompt.value.trim(); const cwd = workspace.value.trim();
    if (!cwd || !text) { status.textContent = !cwd ? "请输入工程工作区路径" : "请输入任务内容"; return; }
    const messages = [...(item.messages || []), { role: "user", content: text }];
    const selected = selectedSkillPaths.length ? "\n\n本轮请读取并遵循这些 Skill：" + selectedSkillPaths.join("；") : "";
    selectedSkillPaths = [];
    prompt.value = ""; submit.disabled = true; await save({ cwd, status: "running", prompt: text, messages, log: "", skill_paths: skillPaths(), allow_extra_rules: extra.checked }); await render();
    try {
      const response = await api("/api/local-codex/task", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, prompt: text + selected + (selected && !extra.checked ? "\n只依据本轮指定 Skill 检查，不使用 Skill 以外的规则。" : ""), cwd }) });
      const data = await response.json(); if (!response.ok || !data.ok) throw Error(data.error || "提交失败");
      const timer = scope.setInterval(async () => {
        const result = await (await api("/api/local-codex/task?task_id=" + data.task_id)).json(); if (!result.ok) return;
        const output = formatEvents(result.task.events).map((section) => section.title + "\n" + section.body).join("\n\n") || "（暂无结构化输出）";
        if (result.task.status !== "running") { await save({ cwd, status: result.task.status, prompt: text, messages: [...messages, { role: "assistant", content: output }], log: output }); submit.disabled = false; clearInterval(timer); await render(); }
      }, 700);
    } catch (error) { await save({ cwd, status: "failed", prompt: text, messages: [...messages, { role: "assistant", content: "提交失败：" + error.message }], log: error.message }); submit.disabled = false; await render(); }
  };
  await render();
}
export function unmount() { scope?.dispose(); }




