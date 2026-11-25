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
  localStorage.removeItem("central-client-server");
  async function getCentralAddress() {
    const response = await api("/api/central-server/status", {cache:"no-store"});
    const server = await response.json();
    if (!response.ok || !server.ok) throw new Error(server.error || "无法获取中央服务器连接信息");
    return server.public_url || `http://${location.hostname}:${server.port}`;
  }
  const sessionKey = "central-ai-sessions";
  let sessions = JSON.parse(localStorage.getItem(sessionKey) || "[]").filter(s => s && s.id && Array.isArray(s.messages));
  let active = sessions[0] || null;
  const pendingSessions = new Set();
  const saveSessions = () => localStorage.setItem(sessionKey, JSON.stringify(sessions.slice(0, 30)));
  function renderSessions(){
    const list = $("central-ai-sessions");
    list.innerHTML = sessions.length ? sessions.map(s => `<div class="session-item ${s.id===active?.id?"active":""}" data-id="${escapeHtml(s.id)}"><div class="session-item-title"><strong>▱ ${escapeHtml(s.title)}</strong><button type="button" class="session-rename" aria-label="重命名会话 ${escapeHtml(s.title)}" title="重命名会话">✎</button></div><small><span>● ${escapeHtml(s.state)}</span><em>${escapeHtml(s.time)}</em></small></div>`).join("") : `<div class="session-empty">暂无进行中的会话</div>`;
    list.querySelectorAll(".session-item").forEach(el => {
      const session = sessions.find(s => s.id === el.dataset.id);
      el.onclick = () => { active = session; $("central-ai-title").textContent=active.title; $("central-ai-input").disabled=pendingSessions.has(active.id); renderMessages(); renderSessions(); };
      el.querySelector(".session-rename").onclick = event => {
        event.stopPropagation();
        const name = window.prompt("输入会话名称", session.title);
        if (name === null) return;
        const title = name.trim();
        if (!title) { window.alert("会话名称不能为空"); return; }
        session.title = title;
        saveSessions();
        if (active === session) $("central-ai-title").textContent = title;
        renderSessions();
      };
    });
  }
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
      $("central-client-status").textContent=client.running?"运行中":"已停止"; $("central-client-address").textContent=client.central_server_url||server.public_url||`http://${location.hostname}:${server.port}`;
      $("central-client-files").textContent=client.client_entry_exists?"已找到本机客户端文件":"本机未找到客户端文件"; $("central-client-dir").textContent=client.client_dir||"";
    } catch (localError) {
      $("central-client-status").textContent="本地接入服务未启动"; $("central-client-address").textContent=server.public_url||`http://${location.hostname}:${server.port}`;
      $("central-client-files").textContent="请运行 local_agent（不影响中央服务器查询）";
    }
    const connectionResponse=await api("/api/central-server/connections",{cache:"no-store"}); const snapshot=await connectionResponse.json();
    if(!connectionResponse.ok) throw Error(snapshot.error||`连接查询失败（HTTP ${connectionResponse.status}）`); renderWorkers(snapshot.workers||snapshot.result?.workers||[]);
  }catch(e){$("central-server-status").textContent="状态获取失败"; $("central-server-msg").textContent=e.message;} }
  $("central-server-start").onclick=async()=>{ $("central-server-msg").textContent="正在启动..."; try{const d=await api("/api/central-server/start",{method:"POST"}).then(r=>r.json()); if(!d.ok)throw Error(d.error); $("central-server-msg").textContent="中央服务器启动请求已发送";}catch(e){$("central-server-msg").textContent=`启动失败：${e.message}`;} await refresh();};
  $("central-server-stop").onclick=async()=>{ $("central-server-msg").textContent="正在关闭..."; await api("/api/central-server/stop",{method:"POST"}); await refresh(); };
  $("central-client-start").onclick=async()=>{ const button=$("central-client-start"); button.disabled=true; $("central-client-msg").textContent="正在启动..."; try{const address=await getCentralAddress(); await localApi("/api/central-client/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({central_server_url:address})}); $("central-client-msg").textContent="本机客户端启动请求已发送";}catch(e){$("central-client-msg").textContent=e.message;} finally{button.disabled=false;} await refresh();};
  $("central-client-stop").onclick=async()=>{try{await localApi("/api/central-client/stop",{method:"POST"});$("central-client-msg").textContent="本机客户端已关闭";}catch(e){$("central-client-msg").textContent=e.message;}await refresh();};
  $("central-client-open").onclick=async()=>{const button=$("central-client-open"); button.disabled=true; try{await localApi("/api/central-client/open",{method:"POST"}); $("central-client-update").textContent="已请求打开客户端目录";}catch(e){$("central-client-update").textContent=e.message === "not found" ? "本机 Local Agent 版本过旧，请在设置页下载更新并重启本机服务" : e.message;}finally{button.disabled=false;}};
  $("central-client-download").onclick=async()=>{const button=$("central-client-download"); button.disabled=true; $("central-client-update").textContent="正在下载客户端…"; try{const response=await api("/api/central-client/download",{cache:"no-store"}); if(!response.ok){let message=`下载失败（HTTP ${response.status}）`; try{const data=await response.json(); message=data.error||message;}catch{} throw new Error(message);} const blob=await response.blob(); const url=URL.createObjectURL(blob); const link=document.createElement("a"); link.href=url; link.download="central-client.zip"; document.body.appendChild(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),60000); $("central-client-update").textContent="客户端下载已开始";}catch(e){$("central-client-update").textContent=e.message;}finally{button.disabled=false;}};
  $("central-ai-new").onclick=()=>{const id=`session-${Date.now()}`;active={id,title:"新的机器管理会话",state:"进行中",time:"刚刚",messages:[]};sessions.unshift(active);saveSessions();renderSessions();renderMessages();$("central-ai-title").textContent=active.title;$("central-ai-input").disabled=false;$("central-ai-close").disabled=false;$("central-ai-input").focus();};
  $("central-ai-close").onclick=()=>{if(!active)return; const index=sessions.findIndex(s=>s.id===active.id); if(index>=0)sessions.splice(index,1); active=sessions[0]||null; saveSessions(); $("central-ai-title").textContent=active?.title||"暂无活动会话"; renderMessages(); $("central-ai-input").disabled=!active || pendingSessions.has(active.id); $("central-ai-close").disabled=!active; renderSessions();};
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
      const response = await api("/api/central-ai/chat-stream", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message, session_id:session.codexSessionId || undefined, context:{workers:latestWorkers.map(w=>({machine_id:w.machine_id,hostname:w.hostname,status:w.status,last_seen_at:w.last_seen_at,meta:{local_ips:w.meta?.local_ips||[]}}))}})});
      if (!response.ok) { const data = await response.json(); throw Error(data.error || ("请求失败（HTTP " + response.status + "）")); }
      if (!response.body) throw Error("浏览器不支持读取流式响应");
      let trace = "", completed = false, buffer = "";
      const reader = response.body.getReader(), decoder = new TextDecoder();
      const update = () => { saveSessions(); if (active === session) { renderMessages(); $("central-ai-messages").scrollTop = $("central-ai-messages").scrollHeight; } };
      const consume = line => {
        if (!line.trim()) return;
        const data = JSON.parse(line);
        if (data.type === "error") throw Error(data.error || "Codex 执行失败");
        if (data.type === "event") {
          const event = data.event || {};
          if (event.type === "thread.started" && event.thread_id) { session.codexSessionId = event.thread_id; update(); return; }
          const item = event.item || event, detail = item.text || item.name || item.tool_name || item.message || JSON.stringify(item);
          trace += `<small class="assistant-trace"><b>${escapeHtml(event.type || 'codex.event')}</b> ${escapeHtml(String(detail).slice(0,1200))}</small>`;
          pendingMessage.html = trace + "分析中..."; update();
        } else if (data.type === "complete") {
          if (!data.session_id) throw Error("服务未返回 Codex 会话 ID");
          session.codexSessionId = data.session_id; completed = true;
          pendingMessage.html = trace + escapeHtml(data.reply || ""); update();
        }
      };
      while (true) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), {stream:!done});
        const lines = buffer.split("\n"); buffer = lines.pop(); lines.forEach(consume);
        if (done) { if (buffer.trim()) consume(buffer); break; }
      }
      if (!completed) throw Error("连接中断，未收到执行完成通知");
      await refresh();
    } catch (err) {
      const errorHtml = "请求失败：" + escapeHtml(err.message);
      pendingMessage.html = (pendingMessage.html === "分析中..." ? "" : pendingMessage.html.replace(/分析中\.\.\.$/, "")) + errorHtml;
      if (active === session) renderMessages();
      saveSessions();
    } finally { pendingSessions.delete(session.id); input.disabled = !active || pendingSessions.has(active.id); $("central-ai-messages").scrollTop = $("central-ai-messages").scrollHeight; }
  };  renderSessions();renderMessages();$("central-ai-title").textContent=active?.title||"暂无活动会话";$("central-ai-input").disabled=!active;$("central-ai-close").disabled=!active;await refresh();interval(refresh,3000);
}
export function unmount(){scope?.dispose();}
