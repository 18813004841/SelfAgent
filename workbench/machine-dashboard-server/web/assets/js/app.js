const pageTitles = {
  overview: "总览",
  scheduler: "定时任务",
  "code-review": "代码检查",
  tasks: "任务",
  calendar: "日程",
  docs: "文档",
  manage: "管理",
  "central-server": "中央服务器管理",
  "openai-agent": "OpenAiAgent 管理",
  "local-codex": "本地 Codex",
  "local-codex-task": "Codex 任务",
  settings: "设置",
  "test-scheduler": "测试任务",
  login: "登录",
  users: "用户管理",
};
const pageModules = {
  overview: () => import("./pages/overview.js"),
  scheduler: () => import("./pages/scheduler.js"),
  "code-review": () => import("./pages/code-review.js"),
  tasks: () => import("./pages/tasks.js"),
  calendar: () => import("./pages/calendar.js"),
  docs: () => import("./pages/docs.js"),
  settings: () => import("./pages/settings.js"),
  manage: () => import("./pages/manage.js"),
  "central-server": () => import("./pages/central-server.js"),
  "openai-agent": () => import("./pages/openai-agent.js"),
  "local-codex": () => import("./pages/local-codex.js"),
  "local-codex-task": () => import("./pages/local-codex-task.js"),
  "test-scheduler": () => import("./pages/test-scheduler.js"),
  login: () => import("./pages/login.js"),
  users: () => import("./pages/users.js"),
};
let currentUser;
const levels = {user:1, advanced:2, developer:3, admin:4};
function applyPermissions(root = document) {
  if (!currentUser) return;
  const level = levels[currentUser.role] || 1;
  root.querySelectorAll("[data-page]").forEach(el => {
    const page = el.dataset.page;
    if ((page === "users" && level < 4) || (["central-server", "openai-agent"].includes(page) && level < 3)) el.hidden = true;
  });
  if (level < 2) {
    root.querySelectorAll("#scheduler-start, #scheduler-stop, #schedule-add, #schedule-create, #review-save, #review-run, #review-stop, #review-clear-history, #review-choose, #review-skill-add, .review-skill-row button, [data-delete], .schedule-delete").forEach(el => { el.hidden = true; });
    root.querySelectorAll(".review-bar input, .review-skill input, .review-skill select").forEach(el => { el.disabled = true; });
  }
}
let activeModule;
let navigation = 0;
export async function load(page) {
  const parts = String(page).split("?");
  const name = parts[0];
  const query = parts[1] || "";
  if (!(name in pageTitles)) return;
  const version = ++navigation;
  activeModule?.unmount();
  activeModule = undefined;
  const content = document.querySelector("#content");
  try {
    const response = await fetch(`/pages/${name}.html`, { cache: "no-store" });
    if (!response.ok) throw new Error(`页面加载失败：${response.status}`);
    const html = await response.text();
    const module = pageModules[name] ? await pageModules[name]() : undefined;
    if (version !== navigation) return;
    content.innerHTML = html;
    applyPermissions(content);
    document.querySelector("#title").textContent = pageTitles[name];
    activeModule = module;
    await module?.mount(content, new URLSearchParams(query));
    applyPermissions(content);
  } catch (error) {
    if (version !== navigation) return;
    activeModule?.unmount();
    content.textContent = `加载失败：${error.message}`;
    console.error(error);
  }
}
async function boot() {
  const session = await fetch("/api/auth/session", {cache:"no-store"}).then(r=>r.json());
  if (!session.user) { document.querySelector("#sidebar").hidden=true; await load("login"); return; }
  currentUser = session.user;
  new MutationObserver(() => applyPermissions()).observe(document.querySelector("#content"), {childList:true, subtree:true});
  const allowed = new Set(session.user.modules); document.querySelector("#sidebar").hidden=false;
  document.querySelectorAll("#sidebar [data-page]").forEach(b=>{ if(!allowed.has(b.dataset.page)) b.hidden=true; });
  if (session.user.is_admin) { const b=document.createElement("button"); b.dataset.page="users"; b.textContent="用户管理"; document.querySelector("#sidebar").insertBefore(b, document.querySelector("#collapse")); }
  const out=document.createElement("button"); out.id="logout"; out.textContent=`${session.user.display_name || session.user.username} · 退出`; out.onclick=async()=>{await fetch("/api/auth/logout",{method:"POST"}); location.reload();}; document.querySelector("#sidebar").insertBefore(out, document.querySelector("#collapse"));
  const first = [...document.querySelectorAll("#sidebar [data-page]")].find(b=>!b.hidden);
  if (!first) {
    document.querySelector("#title").textContent = "暂无可用功能";
    document.querySelector("#content").innerHTML = `<section class="access-denied card"><div class="access-icon">🔒</div><h1>暂无功能权限</h1><p>当前账号还没有开放任何功能，请联系管理员授权后再访问工作台。</p><p class="muted">账号：${session.user.display_name || session.user.username}</p></section>`;
    return;
  }
  await load(first.dataset.page);
}
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-page]");
  if (button) load(button.dataset.page);
});
document.querySelector("#collapse").onclick = () => {
  const sidebar = document.querySelector(".sidebar");
  sidebar.classList.toggle("collapsed");
  document.querySelector("#collapse").textContent = sidebar.classList.contains(
    "collapsed",
  )
    ? "›"
    : "‹";
};
boot().catch(()=>load("login"));
