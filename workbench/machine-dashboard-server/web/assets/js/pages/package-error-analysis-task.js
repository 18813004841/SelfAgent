const STAGES = ["created", "parse", "jenkins", "worker", "remote", "mounted", "detect", "result"];
const optional = new Set(["jenkins", "worker", "mounted"]);
export async function mount() {
  const q = (s) => document.querySelector(s);
  const input=q("#analysis-input"), log=q("#analysis-log"), title=q("#analysis-detail-title"), status=q("#analysis-detail-status"), state=q("#analysis-output-state"), msg=q("#analysis-message"), finish=q("#finish-analysis"), fill=q("#progress-fill"), pct=q("#progress-percent"), caption=q("#progress-caption");
  let polling=false;
  const renderProgress = (task) => {
    const events=task?.events || [], text=events.map(e=>e.message||"").join(" ");
    const active = new Set(), done = new Set(), skipped = new Set();
    if (task) { done.add("created"); active.add("parse"); }
    if (text.includes("输入解析完成")) { done.add("parse"); active.delete("parse"); }
    if (text.includes("Jenkins 构建参数补全完成")) done.add("jenkins"); else if (text.includes("未配置") || text.includes("参数读取失败")) skipped.add("jenkins"); else if (task) active.add("jenkins");
    if (text.includes("Worker 查询完成") || text.includes("Worker 查询失败")) { done.add("worker"); active.delete("worker"); } else if (text.includes("未配置在线 Worker")) skipped.add("worker");
    if (text.includes("使用在线 Worker 日志") || text.includes("Worker 日志读取完成")) { done.add("remote"); active.delete("remote"); }
    if (text.includes("转入网盘") || text.includes("网盘日志查找完成")) { done.add("remote"); done.add("mounted"); active.delete("remote"); active.delete("mounted"); }
    if (text.includes("日志查找完成") && !text.includes("mounted:not-found")) done.add("mounted");
    if (text.includes("失败 step 与核心证据分析完成")) { done.add("detect"); done.add("result"); active.clear(); }
    if (task?.status === "failed") { const last=events.at(-1)?.message||""; if (last.includes("日志")) active.add("mounted"); }
    ["jenkins","worker","mounted"].forEach(s => { if (!done.has(s) && !active.has(s) && task && ((s === "mounted" && !text.includes("网盘")) || (s === "jenkins" && text.includes("未配置")) || (s === "worker" && text.includes("未配置")))) skipped.add(s); });
    const relevant=STAGES.filter(s=>!skipped.has(s)); const completeCount=relevant.filter(s=>done.has(s)).length; const percentage=task ? Math.round(completeCount/relevant.length*100) : 0;
    document.querySelectorAll(".progress-node").forEach(node=>{ const s=node.dataset.step; node.classList.toggle("done",done.has(s)); node.classList.toggle("active",active.has(s)); node.classList.toggle("skipped",skipped.has(s)); node.classList.toggle("failed",task?.status === "failed" && active.has(s)); });
    fill.style.height = `${Math.max(0, percentage-4)}%`; pct.textContent=`${percentage}%`; caption.textContent=task?.status === "failed" ? `流程失败 · ${completeCount} 个阶段已完成` : task?.status === "completed" ? "分析完成 · 全部阶段已结束" : `${active.size ? "当前节点进行中" : "准备开始"} · ${completeCount} 个阶段已完成`;
  };
  const render = (task) => { renderProgress(task); if(!task){ title.textContent="新建报错分析任务"; status.textContent="待提交"; state.textContent="等待输入"; log.textContent="提交后将显示日志定位、失败阶段和分析结果。"; return; } title.textContent=`报错分析任务 ${task.id}`; status.textContent=task.status; status.classList.toggle("done", task.status === "completed"); input.value=task.input_text || input.value || ""; log.textContent=(task.events||[]).map(e=>`[${e.time}] ${e.message}`).join("\n"); if(task.result?.failed_step) log.textContent += `\n\n失败原因：${task.result.failure_reason||"未确认"}\n失败阶段：${task.result.failed_step}\n失败证据：\n${(task.result.evidence||[]).join("\n")}\n修复建议：${task.result.repair_suggestion||"请根据该失败阶段检查对应构建模块。"}`; if(task.error) log.textContent += `\n\n${task.error}`; state.textContent=task.status === "completed" ? "分析完成" : task.status === "failed" ? "分析失败" : "分析中…"; };
  const load=async()=>{ if(!window.__analysisTaskId) return render(null); const r=await fetch(`/api/package-error-analysis/tasks/${encodeURIComponent(window.__analysisTaskId)}`), d=await r.json(); if(!r.ok||!d.ok) throw new Error(d.error||"无法读取分析任务"); render(d.task); };
  const poll=async(id)=>{ if(polling)return; polling=true; try{while(true){await new Promise(r=>setTimeout(r,800)); const r=await fetch(`/api/package-error-analysis/tasks/${encodeURIComponent(id)}`),d=await r.json(); if(!r.ok||!d.ok)throw new Error(d.error||"读取任务状态失败"); render(d.task); if(["completed","failed"].includes(d.task.status))break;}}finally{polling=false;}};
  q("#run-analysis").onclick=async()=>{const text=input.value.trim();if(!text){msg.textContent="请先输入打包报错信息";return;}msg.textContent="";try{const r=await fetch("/api/package-error-analysis/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({input:text})}),d=await r.json();if(!r.ok||!d.ok)throw new Error(d.error||"任务创建失败");window.__analysisTaskId=d.task.id;render(d.task);await poll(d.task.id);}catch(e){msg.textContent=e.message;state.textContent="分析失败";}};
  finish.onclick=()=>{status.textContent="已结束";status.classList.add("done");msg.textContent="任务已结束";};
  try{await load();}catch(e){msg.textContent=e.message;state.textContent="读取失败";}
}
export function unmount() {}
