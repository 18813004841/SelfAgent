import { createPageScope } from "../shared/page-scope.js";
let scope, timer;
const api = (p, o) => scope.fetch(p, o);
const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
export async function mount() {
  scope=createPageScope(); const box=document.getElementById("server-messages"), input=document.getElementById("server-input"), send=document.getElementById("server-send"), cancel=document.getElementById("server-cancel"), restart=document.getElementById("server-restart"), status=document.getElementById("server-status");
  const render = messages => { box.innerHTML=(messages||[]).map(m=>`<div class="card" style="margin:8px 0"><b>${m.role === "user" ? "你" : "Codex"}</b><pre style="white-space:pre-wrap">${esc(m.content)}</pre></div>`).join(""); box.scrollTop=box.scrollHeight; };
  const session=await (await api("/api/server-maintenance/session")).json(); render(session.messages); status.textContent=`工作区：${session.workspace}`;
  async function poll(id){ const d=await (await api(`/api/server-maintenance/task?task_id=${encodeURIComponent(id)}`)).json(); if(!d.ok)return; if(d.task?.status!=="running"){clearInterval(timer); timer=null; send.disabled=false; cancel.hidden=true; render(d.task.messages); status.textContent=d.task.status === "completed" ? "执行完成" : (d.task.error || "执行失败");} }
  send.onclick=async()=>{ const message=input.value.trim(); if(!message)return status.textContent="请输入维护内容"; send.disabled=true; cancel.hidden=false; status.textContent="Codex 执行中…"; try { const d=await (await api("/api/server-maintenance/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message})})).json(); if(!d.ok)throw Error(d.error); input.value=""; timer=scope.setInterval(()=>poll(d.task_id),700); } catch(e){send.disabled=false;cancel.hidden=true;status.textContent="提交失败："+e.message;} };
  cancel.onclick=async()=>{cancel.disabled=true; await api("/api/server-maintenance/cancel",{method:"POST"}); status.textContent="正在取消…";};
  restart.onclick=async()=>{restart.disabled=true; status.textContent="正在重启服务器…"; try { const d=await (await api("/api/server-maintenance/restart",{method:"POST"})).json(); if(!d.ok)throw Error(d.error); const wait=scope.setInterval(async()=>{try{const h=await (await fetch("/api/health",{cache:"no-store"})).json();if(h.ok){clearInterval(wait);restart.disabled=false;status.textContent="服务器已恢复";}}catch{}},1000);}catch(e){restart.disabled=false;status.textContent="重启失败："+e.message;}};
}
export function unmount(){if(timer)clearInterval(timer);scope?.dispose();}
