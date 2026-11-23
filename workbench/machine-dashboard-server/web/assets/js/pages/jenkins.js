import { mountPermissions } from "./jenkins-permissions.js";
import { createPageScope } from "../shared/page-scope.js";
let scope;

export async function mount() {
  scope = createPageScope();
  const form = document.querySelector("#jenkins-form"), ip = document.querySelector("#jenkins-ip"),
    scheme = document.querySelector("#jenkins-scheme"), port = document.querySelector("#jenkins-port"),
    save = document.querySelector("#jenkins-save"), cancel = document.querySelector("#jenkins-cancel"),
    message = document.querySelector("#jenkins-message"), list = document.querySelector("#jenkins-list"),
    status = document.querySelector("#jenkins-list-status"), title = document.querySelector("#jenkins-form-title");
  let editing = null, refreshing = false, refreshAgain = false, busy = false;
  const users = document.querySelector("#jenkins-users"), targets = document.querySelector("#jenkins-register-targets"),
    registerForm = document.querySelector("#jenkins-register-form"), registerMessage = document.querySelector("#jenkins-register-message"),
    registerResults = document.querySelector("#jenkins-register-results"), registerSubmit = document.querySelector("#jenkins-register-submit");
  let registerBusy = false;
  async function initUsers() {
    try {
      const session = await request("/api/auth/session", {cache:"no-store"});
      users.hidden = false;
      document.querySelector("#jenkins-permissions-tab").hidden = !session.user?.is_admin;
      document.querySelectorAll("[data-jenkins-manage]").forEach(section => { section.hidden = !session.user?.modules?.includes("manage"); });
      if (session.user?.is_admin) mountPermissions(scope);
    } catch { users.hidden = true; }
  }
  function renderTargets(items) {
    const selected = new Set([...targets.querySelectorAll("input:checked")].map(input => input.value));
    targets.replaceChildren();
    if (!items.length) { targets.textContent = "请先添加 Jenkins"; return; }
    for (const item of items) {
      const label = document.createElement("label"), input = document.createElement("input");
      input.type = "checkbox"; input.value = item.ip; input.checked = selected.has(item.ip); input.disabled = registerBusy;
      label.append(input, document.createTextNode(` ${item.ip}`)); targets.append(label);
    }
  }
  registerForm.onsubmit = async event => {
    event.preventDefault(); if (registerBusy) return;
    const ips = [...targets.querySelectorAll("input:checked")].map(input => input.value),
      password = document.querySelector("#jenkins-register-password"), confirm = document.querySelector("#jenkins-register-confirm");
    if (!ips.length) { registerMessage.textContent = "请选择 Jenkins"; return; }
    if (password.value !== confirm.value) { registerMessage.textContent = "两次输入的密码不一致"; return; }
    registerBusy = true; registerSubmit.disabled = true; registerMessage.textContent = "正在注册，请稍候..."; registerResults.replaceChildren();
    try {
      const body = {ips, username:document.querySelector("#jenkins-register-username").value.trim(), fullname:document.querySelector("#jenkins-register-fullname").value.trim(), email:document.querySelector("#jenkins-register-email").value.trim(), password:password.value};
      const data = await request("/api/jenkins/register", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
      for (const result of data.results) { const li = document.createElement("li"); li.textContent = `${result.ip}：${result.message}`; registerResults.append(li); }
      registerMessage.textContent = "处理完成，请查看各实例结果。";
    } catch (error) { registerMessage.textContent = `请求失败：${error.message}。请先检查目标 Jenkins 中的账号，再决定是否重试。`; }
    finally { password.value = ""; confirm.value = ""; registerBusy = false; registerSubmit.disabled = false; targets.querySelectorAll("input").forEach(input => { input.disabled = false; }); }
  };
  function reset() {
    editing = null; form.reset(); title.textContent = "添加 Jenkins";
    save.textContent = "添加"; cancel.hidden = true;
  }
  async function request(url, options) {
    const response = await scope.fetch(url, options);
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || `请求失败 (${response.status})`);
    return data;
  }
  function render(items) {
    list.replaceChildren();
    renderTargets(items);
    status.textContent = items.length ? "" : "暂无 Jenkins，使用上方表单添加。";
    for (const item of items) {
      const row = document.createElement("div"); row.className = "jenkins-row";
      const link = document.createElement("a"); link.href = item.url; link.target = "_blank";
      link.rel = "noopener noreferrer"; link.className = "jenkins-link";
      const name = document.createElement("strong"); name.textContent = item.ip;
      const info = document.createElement("span");
      const online = { online: "在线", offline: "离线", unknown: "未知" };
      const connected = { connected: "已连接", disconnected: "未连接", unknown: "未知" };
      info.textContent = `Jenkins：${online[item.online]} · 中央服务器：${connected[item.connected]} · ${item.scheme.toUpperCase()}:${item.port}`;
      const edit = document.createElement("button"); edit.type = "button"; edit.textContent = "修改";
      edit.onclick = () => { editing = item.ip; ip.value = item.ip; scheme.value = item.scheme; port.value = item.port; title.textContent = "修改 Jenkins"; save.textContent = "保存"; cancel.hidden = false; message.textContent = ""; ip.focus(); };
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "删除";
      remove.onclick = async () => {
        if (busy || !window.confirm(`确定删除 ${item.ip}？`)) return;
        busy = true; remove.disabled = true; save.disabled = true;
        try { await request("/api/jenkins/delete", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ip:item.ip})}); if (editing === item.ip) reset(); message.textContent = "已删除"; await refresh(); }
        catch (error) { message.textContent = `删除失败：${error.message}`; }
        finally { busy = false; remove.disabled = false; save.disabled = false; }
      };
      link.append(name, info); row.append(link, edit, remove); list.append(row);
    }
  }
  async function refresh() {
    if (refreshing) { refreshAgain = true; return; }
    refreshing = true;
    try { const data = await request("/api/jenkins", {cache:"no-store"}); render(data.servers); }
    catch (error) { status.textContent = `加载失败：${error.message}`; }
    finally { refreshing = false; if (refreshAgain) { refreshAgain = false; await refresh(); } }
  }
  cancel.onclick = reset;
  form.onsubmit = async event => {
    event.preventDefault(); if (busy) return;
    busy = true; save.disabled = true; message.textContent = "正在保存...";
    try {
      const body = {ip:ip.value.trim(), scheme:scheme.value, port:port.value};
      if (editing !== null) body.old_ip = editing;
      await request("/api/jenkins/save", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
      reset(); message.textContent = "已保存"; await refresh();
    } catch (error) { message.textContent = `保存失败：${error.message}`; }
    finally { busy = false; save.disabled = false; }
  };
  await initUsers();
  scope.setInterval(refresh, 15000);
  await refresh();
}
export function unmount() { scope?.dispose(); }
