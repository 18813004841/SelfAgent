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
};
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
    document.querySelector("#title").textContent = pageTitles[name];
    activeModule = module;
    await module?.mount(content, new URLSearchParams(query));
  } catch (error) {
    if (version !== navigation) return;
    activeModule?.unmount();
    content.textContent = `加载失败：${error.message}`;
    console.error(error);
  }
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
load("overview");
