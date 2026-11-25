import { createPageScope } from "../shared/page-scope.js";

const STAGES = ["parse", "archive", "worker", "analysis", "save_result"];
const LABELS = { parse: "解析输入和补全参数", archive: "读取归档日志", worker: "读取打包机日志", analysis: "分析日志", save_result: "保存分析结果" };
let scope;

// Older tasks have only the original human-readable lifecycle events.
export function progressForTask(task) {
  const stages = Object.fromEntries(STAGES.map(name => [name, "pending"]));
  for (const event of task?.events || []) {
    let node = event.data?.node, phase = event.data?.phase;
    if (!STAGES.includes(node) || !["start", "completed", "failed", "skipped"].includes(phase)) {
      node = STAGES.find(name => (event.message || "").startsWith(`${LABELS[name]}：`));
      const message = event.message || "";
      phase = message.includes("：开始") ? "start" : message.includes("：已跳过") ? "skipped" : message.includes("：结束，执行失败") ? "failed" : message.includes("：结束") ? "completed" : null;
    }
    if (node && phase) stages[node] = phase === "start" ? "active" : phase === "completed" ? "done" : phase;
  }
  // Tasks created before lifecycle events were introduced still have useful milestones.
  const text = (task?.events || []).map(event => event.message || "").join("\n");
  if (stages.parse === "pending" && text.includes("输入解析完成")) stages.parse = "done";
  if (stages.archive === "pending" && (text.includes("网盘日志查找完成") || text.includes("网盘日志为空") || text.includes("网盘日志读取失败"))) stages.archive = "done";
  if (stages.worker === "pending" && text.includes("使用网盘归档日志")) stages.worker = "skipped";
  if (stages.worker === "pending" && text.includes("使用在线 Worker 日志")) stages.worker = "done";
  if (task?.status === "completed") for (const name of STAGES) if (stages[name] === "pending") stages[name] = name === "worker" && stages.worker === "skipped" ? "skipped" : "done";
  if (task?.status === "failed") {
    const active = STAGES.find(name => stages[name] === "active");
    if (active) stages[active] = "failed";
  }
  const done = STAGES.filter(name => stages[name] === "done").length;
  const skipped = STAGES.filter(name => stages[name] === "skipped").length;
  const percent = task ? Math.round((done + skipped) / STAGES.length * 100) : 0;
  return { stages, done, skipped, percent };
}

export async function mount() {
  scope = createPageScope();
  const pageScope = scope;
  const q = s => document.querySelector(s);
  const input=q("#analysis-input"), log=q("#analysis-log"), title=q("#analysis-detail-title"), status=q("#analysis-detail-status"), state=q("#analysis-output-state"), msg=q("#analysis-message"), finish=q("#finish-analysis"), pct=q("#progress-percent"), caption=q("#progress-caption"), run=q("#run-analysis");
  let polling = false, busy = false;
  const renderProgress = task => {
    const progress = progressForTask(task);
    document.querySelectorAll(".progress-node").forEach(node => {
      const stage = progress.stages[node.dataset.step];
      for (const cls of ["done", "active", "skipped", "failed"]) node.classList.toggle(cls, stage === cls);
      const label = ({pending:"等待",active:"进行中",done:"已完成",skipped:"已跳过",failed:"失败"})[stage];
      node.setAttribute("aria-label", `${LABELS[node.dataset.step]}：${label}`);
      const statusLabel = node.querySelector(".flow-status");
      if (statusLabel) statusLabel.textContent = label;
    });
    const worker = progress.stages.worker;
    const archiveUsed = worker === "skipped";
    const workerUsed = ["active", "done", "failed"].includes(worker);
    const edgeStates = {
      "parse-archive": progress.stages.parse === "done",
      "archive-analysis": archiveUsed,
      "archive-worker": workerUsed,
      "worker-analysis": worker === "done",
      "analysis-save": progress.stages.analysis === "done",
    };
    document.querySelectorAll(".flow-links [data-edge]").forEach(edge => {
      edge.classList.toggle("taken", Boolean(edgeStates[edge.dataset.edge]));
      edge.classList.toggle("failed", edge.dataset.edge === "worker-failure" && worker === "failed");
    });
    const failure = q("#flow-failure");
    if (failure) {
      const failed = task?.status === "failed";
      failure.classList.toggle("failed", failed);
      failure.querySelector(".flow-status").textContent = failed ? "已记录失败" : "等待";
    }
    pct.textContent = `${progress.percent}%`;
    const active = STAGES.find(name => progress.stages[name] === "active");
    caption.textContent = task?.status === "failed" ? `流程失败 · ${progress.done} 个节点已完成` : task?.status === "completed" ? `分析完成 · ${progress.done} 个节点完成，${progress.skipped} 个跳过` : active ? `正在执行：${LABELS[active]} · ${progress.done} 个节点已完成` : `准备开始 · ${progress.done} 个节点已完成`;
  };
  const render = task => {
    renderProgress(task);
    if (!task) { title.textContent="新建报错分析任务"; status.textContent="待提交"; state.textContent="等待输入"; log.textContent="提交后将显示日志定位、失败阶段和分析结果。"; return; }
    title.textContent=`报错分析任务 ${task.id}`; status.textContent=task.status; status.classList.toggle("done", task.status === "completed");
    input.value=task.input_text || input.value || "";
    log.textContent=(task.events||[]).map(e=>`[${e.time}] ${e.message}`).join("\n");
    if(task.result?.failed_step) log.textContent += `\n\n失败原因：${task.result.failure_reason||"未确认"}\n失败阶段：${task.result.failed_step}\n失败证据：\n${(task.result.evidence||[]).join("\n")}\n修复建议：${task.result.repair_suggestion||"请根据该失败阶段检查对应构建模块。"}`;
    if(task.error) log.textContent += `\n\n${task.error}`;
    state.textContent=task.status === "completed" ? "分析完成" : task.status === "failed" ? "分析失败" : "分析中…";
  };
  const read = async id => {
    const r=await pageScope.fetch(`/api/package-error-analysis/tasks/${encodeURIComponent(id)}`), d=await r.json();
    if(!r.ok||!d.ok) throw new Error(d.error||"无法读取分析任务");
    render(d.task); return d.task;
  };
  const poll = id => {
    if (polling) return;
    polling = true; run.disabled = true;
    let checking = false;
    const timer = pageScope.setInterval(async () => {
      if (checking) return;
      checking = true;
      try {
        const task = await read(id);
        if (["completed", "failed"].includes(task.status)) { window.clearInterval(timer); polling=false; run.disabled=false; }
      } catch (e) { window.clearInterval(timer); polling=false; run.disabled=false; msg.textContent=e.message; state.textContent="读取失败"; }
      finally { checking=false; }
    }, 800);
  };
  run.onclick=async()=>{
    if (busy || polling) return;
    const text=input.value.trim(); if(!text){msg.textContent="请先输入打包报错信息";return;}
    busy=true; run.disabled=true; msg.textContent="";
    try {
      const r=await pageScope.fetch("/api/package-error-analysis/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({input:text})}), d=await r.json();
      if(!r.ok||!d.ok) throw new Error(d.error||"任务创建失败");
      window.__analysisTaskId=d.task.id; render(d.task);
      if (!["completed", "failed"].includes(d.task.status)) poll(d.task.id);
    } catch(e){msg.textContent=e.message;state.textContent="分析失败";}
    finally { busy=false; if (!polling) run.disabled=false; }
  };
  finish.onclick=()=>{ window.dispatchEvent(new CustomEvent("workbench:navigate", {detail:"package-error-analysis"})); };
  try { if (!window.__analysisTaskId) render(null); else { const task=await read(window.__analysisTaskId); if (!["completed", "failed"].includes(task.status)) poll(task.id); } }
  catch(e){msg.textContent=e.message;state.textContent="读取失败";}
}
export function unmount() { if (scope) scope.dispose(); scope = undefined; }
