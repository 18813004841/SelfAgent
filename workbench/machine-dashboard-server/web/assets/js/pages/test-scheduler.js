import { load } from "../app.js";
import { createPageScope } from "../shared/page-scope.js";
let scope;
const fetch = (...args) => scope.fetch(...args);
const setInterval = (...args) => scope.setInterval(...args);
async function initTestScheduler() {
  if (window.__schedulerTimer) clearInterval(window.__schedulerTimer);
  document.getElementById("test-back").onclick = () => load("scheduler");
  async function refresh() {
    try {
      const r = await fetch(
        "/api/schedules/" + encodeURIComponent(window.__selectedTaskId),
        { cache: "no-store" },
      );
      const d = await r.json();
      if (!r.ok) throw Error(d.error || "读取失败");
      const t = d.schedule;
      document.getElementById("test-name").textContent = t.name;
      document.getElementById("test-time").textContent =
        (t.run_type === 2 ? "执行一次 " : "每天 ") +
        (t.run_time || t.schedule_expr);
      document.getElementById("test-status").textContent =
        {
          running: "执行中",
          succeeded: "成功",
          failed: "失败",
          cancelled: "已取消",
        }[t.last_status] ||
        t.last_status ||
        "未执行";
      document.getElementById("test-progress").textContent =
        (t.progress_current || 0) + "/" + (t.progress_total || 10);
      document.getElementById("test-runs").textContent =
        (t.runs || [])
          .map(
            (x) =>
              new Date(x.started_at * 1000).toLocaleString() +
              " " +
              x.status +
              " " +
              (x.output || x.error || ""),
          )
          .join("\n") || "暂无执行记录";
    } catch (e) {
      document.getElementById("test-runs").textContent = e.message;
    }
  }
  await refresh();
  window.__testTimer = setInterval(refresh, 1000);
}
export async function mount() {
  scope = createPageScope();
  await initTestScheduler();
}
export function unmount() {
  scope?.dispose();
}
