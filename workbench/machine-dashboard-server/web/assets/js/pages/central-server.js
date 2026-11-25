import { createPageScope } from "../shared/page-scope.js";
import { localApi, LOCAL_AGENT_ORIGIN } from "../shared/local-agent.js";
let scope;
const api = (...args) => scope.fetch(...args);
const interval = (...args) => scope.setInterval(...args);
const escapeHtml = text => String(text).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[c]));
  let latestWorkers = [];
export async function mount() {
  scope = createPageScope();
  const $ = id => document.getElementById(id);
  const serverInput = $("central-client-server"); serverInput.value = `${location.protocol}//${location.hostname}:18765`;
  const sessionKey = "central-ai-sessions";
  let sessions = JSON.parse(localStorage.getItem(sessionKey) || "[]").filter(s => s && s.id && Array.isArray(s.messages));
  let active = sessions[0] || null;
  const pendingSessions = new Set();
  const saveSessions = () => localStorage.setItem(sessionKey, JSON.stringify(sessions.slice(0, 30)));
  function renderSessions(){ $("central-ai-sessions").innerHTML=sessions.length?sessions.map(s=>`<div class="session-item ${s.id===active?.id?"active":""}" data-id="${s.id}"><strong>▱ ${escapeHtml(s.title)}</strong><small><span>● ${s.state}</span><em>${s.time}</em></small></div>`).join(""): `<div class="session-empty">暂无进行中的会话</div>`; document.querySelectorAll(".session-item").forEach(el=>el.onclick=()=>{active=sessions.find(s=>s.id===el.dataset.id)||active; $("central-ai-title").textContent=active.title; $("central-ai-input").disabled=pendingSessions.has(active.id); renderMessages(); renderSessions();}); }
  function renderMessages(){ const box=$("central-ai-messages"); if(!active){box.innerHTML='<div class="session-empty">请新建会话开始咨询。</div>';return;} box.innerHTML=active.messages.map(m=>`<div class="chat-bubble ${m.role==='user'?'user':'assistant'}">${m.html}</div>`).join('') || '<div class="chat-bubble assistant">你好，我可以帮助你查询已连接机器的状态、资源和日志。</div>'; }
  function renderWorkers(workers=[]){ latestWorkers=workers; $("central-worker-count").textContent=`(${workers.filter(w=>w.status==="online").length})`; $("central-workers").innerHTML=workers.length?workers.slice(0,4).map(w=>`<div class="worker-item"><span>▣</span><div class="machine"><b>${escapeHtml(w.hostname||w.machine_id)}</b><small>${escapeHtml((w.meta?.local_ips||[])[0]||"未上报 IP")}</small></div><span class="online">● ${w.status==="online"?"在线":"离线"}</span></div>`).join(""): `<div class="worker-item"><small>暂无已连接客户端</small></div>`; }
  async function refresh(){ try{
    const response=await api("/api/central-server/status",{cache:"no-store"}),server=await response.json();
    if(!response.ok || server.ok === false) throw Error(server.error||`状态查询失败（HTTP ${response.status}）`);
    $("central-server-status").textContent=server.running === true?"运行中":"已停止"; $("central-server-port").textContent=server.port||18765;
    // Local Agent only manages this browser's local client. Its absence must
    // not prevent the server-side worker list from being loaded.
    try {
      const client=await localApi("/api/central-client/status");
      $("central-client-status").textContent=client.running?"运行中":"已停止"; $("central-client-address").textContent=serverInput.value||"未配置";
      $("central-client-files").textContent=client.client_entry_exists?"已找到本机客户端文件":"本机未找到客户端文件"; $("central-client-dir").textContent=client.client_dir||"";
    } catch (localError) {
      $("central-client-status").textContent="本地接入服务未启动"; $("central-client-address").textContent=serverInput.value||"未配置";
      $("central-client-files").textContent="请运行 local_agent（不影响中央服务器查询）";
    }
    const connectionResponse=await api("/api/central-server/connections",{cache:"no-store"}); const snapshot=await connectionResponse.json();
    if(!connectionResponse.ok) throw Error(snapshot.error||`连接查询失败（HTTP ${connectionResponse.status}）`); renderWorkers(snapshot.workers||snapshot.result?.workers||[]);
  }catch(e){$("central-server-status").textContent="状态获取失败"; $("central-server-msg").textContent=e.message;} }
  $("central-server-start").onclick=async()=>{ $("central-server-msg").textContent="正在启动..."; try{const d=await api("/api/central-server/start",{method:"POST"}).then(r=>r.json()); if(!d.ok)throw Error(d.error); $("central-server-msg").textContent="中央服务器启动请求已发送";}catch(e){$("central-server-msg").textContent=`启动失败：${e.message}`;} await refresh();};
  $("central-server-stop").onclick=async()=>{ $("central-server-msg").textContent="正在关闭..."; await api("/api/central-server/stop",{method:"POST"}); await refresh(); };
  $("central-client-start").onclick=async()=>{ $("central-client-msg").textContent="正在启动..."; try{localStorage.setItem("central-client-server",serverInput.value.trim()); await localApi("/api/central-client/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({central_server_url:serverInput.value.trim()})}); $("central-client-msg").textContent="本机客户端启动请求已发送";}catch(e){$("central-client-msg").textContent=e.message;} await refresh();};
  $("central-client-stop").onclick=async()=>{try{await localApi("/api/central-client/stop",{method:"POST"});$("central-client-msg").textContent="本机客户端已关闭";}catch(e){$("central-client-msg").textContent=e.message;}await refresh();};
  $("central-ai-new").onclick=()=>{const id=`session-${Date.now()}`;active={id,title:"新的机器管理会话",state:"进行中",time:"刚刚",messages:[]};sessions.unshift(active);saveSessions();renderSessions();renderMessages();$("central-ai-input").disabled=false;$("central-ai-close").disabled=false;$("central-ai-input").focus();};
  $("central-ai-close").onclick=()=>{if(!active)return; const index=sessions.findIndex(s=>s.id===active.id); if(index>=0)sessions.splice(index,1); active=sessions[0]||null; saveSessions(); $("central-ai-title").textContent=active?.title||"暂无活动会话"; renderMessages(); $("central-ai-input").disabled=!active; $("central-ai-close").disabled=!active; renderSessions();};
    $("central-ai-form").onsubmit = async e => {
    e.preventDefault();
    const input = $("central-ai-input"), message = input.value.trim();
    if (!message || !active || pendingSessions.has(active.id)) return;
    const session = active;
    pendingSessions.add(session.id);
    $("central-ai-messages").insertAdjacentHTML("beforeend", '<div class="chat-bubble user">' + escapeHtml(message) + '</div>');
    active.messages.push({role:"user", html:escapeHtml(message)}); saveSessions();
    input.value = ""; input.disabled = true;
    const pendingMessage = {role:"assistant", html:"分析中..."};
    active.messages.push(pendingMessage); saveSessions();
    $("central-ai-messages").insertAdjacentHTML("beforeend", '<div class="chat-bubble assistant">分析中...</div>');
    $("central-ai-messages").scrollTop = $("central-ai-messages").scrollHeight;
    try {
      const response = await api("/api/central-ai/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message, session_id:session.codexSessionId || undefined, context:{workers:latestWorkers.map(w=>({machine_id:w.machine_id,hostname:w.hostname,status:w.status,last_seen_at:w.last_seen_at,meta:{local_ips:w.meta?.local_ips||[]}}))}})});
      const data = await response.json();
      if (!response.ok || !data.ok) throw Error(data.error || ("请求失败（HTTP " + response.status + "）"));
      if (!data.session_id) throw Error("服务未返回 Codex 会话 ID");
      session.codexSessionId = data.session_id;
      const workers = data.result && data.result.workers || [];
      const detail = workers.map(w => '<li><strong>' + escapeHtml(w.hostname || w.machine_id) + '</strong>：' + (w.status === "online" ? "在线" : "离线") + '</li>').join("");
      let task = "";
      if (data.task) task = '<div class="task-card"><b>已提交中央服务器任务</b><p>目标：' + escapeHtml((data.worker && (data.worker.hostname || data.worker.machine_id)) || "") + '<br>任务 ID：' + escapeHtml(data.task.task_id || "") + '<br>状态：' + escapeHtml(data.task.status || "queued") + '</p></div>';
      const trace = (data.events||[]).filter(e=>e && e.type !== 'thread.started').map(e=>{
        const item=e.item||e;
        const label=e.type||'codex.event';
        const text=item.text||item.name||item.tool_name||item.message||'';
        const detail=text||JSON.stringify(item);
        return `<small class="assistant-trace"><b>${escapeHtml(label)}</b> ${escapeHtml(String(detail).slice(0,1200))}</small>`;
      }).join('');
      const assistantHtml = trace + escapeHtml(data.reply || "") + (detail ? '<ul>' + detail + '</ul>' : "") + task;
      pendingMessage.html = assistantHtml;
      if (active === session) renderMessages();
      saveSessions();
      // The assistant response is already a fresh connection snapshot. Render
      // it immediately, then refresh from the connections endpoint as well.
      if (data.result && Array.isArray(data.result.workers)) renderWorkers(data.result.workers);
      await refresh();
    } catch (err) {
      const errorHtml = "请求失败：" + escapeHtml(err.message);
      pendingMessage.html = errorHtml;
      if (active === session) renderMessages();
      saveSessions();
    } finally { pendingSessions.delete(session.id); input.disabled = !active || pendingSessions.has(active.id); $("central-ai-messages").scrollTop = $("central-ai-messages").scrollHeight; }
  };  renderSessions();renderMessages();$("central-ai-title").textContent=active?.title||"暂无活动会话";$("central-ai-input").disabled=!active;$("central-ai-close").disabled=!active;await refresh();interval(refresh,3000);
}
export function unmount(){scope?.dispose();}
