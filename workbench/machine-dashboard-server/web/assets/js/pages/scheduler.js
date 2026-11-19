import { load } from "../app.js";
import { createPageScope } from "../shared/page-scope.js";
let scope;
const fetch = (...args) => scope.fetch(...args);
const setInterval = (...args) => scope.setInterval(...args);
async function initScheduler() {
  const state = document.getElementById("scheduler-status"),
    msg = document.getElementById("scheduler-msg"),
    list = document.getElementById("schedule-list"),
    detail = document.getElementById("schedule-detail");
  const statusText = (value) =>
    ({
      success: "成功",
      succeeded: "成功",
      failed: "失败",
      running: "执行中",
      cancelled: "已取消",
      cancelling: "取消中",
    })[value] ||
    value ||
    "尚未构建";
  async function refresh(statusOnly = false) {
    try {
      const d = await fetch("/api/scheduler/status", {
        cache: "no-store",
      }).then((r) => r.json());
      state.textContent = d.running ? "运行中" : "已停止";
      state.style.color = d.running ? "green" : "#888";
    } catch (e) {
      state.textContent = "状态未知";
      state.style.color = "#c77";
    }
    if (detail.innerHTML) return;
    try {
      const schedules = await fetch("/api/schedules", {
        cache: "no-store",
      }).then((r) => r.json());
      const rest = (schedules.schedules || []).filter(
        (item) =>
          (item.dispatcher || "scheduler") === "scheduler" &&
          item.enabled !== 0 &&
          item.tool_id !== "code-review-agent",
      );
      const other = document.getElementById("other-schedules");
      if (other) {
        other.replaceChildren();
        rest.forEach((item) => {
          const when =
            item.schedule_type === "daily"
              ? "每天 " + (item.schedule_expr || "04:00")
              : item.schedule_type === "once"
                ? "执行一次"
                : "每 " + (item.schedule_expr || "?") + " 秒";
          const card = document.createElement("div");
          card.className = "schedule-card";
          const name = document.createElement("h4");
          name.textContent = item.name;
          const meta = document.createElement("div");
          meta.className = "schedule-meta";
          const label = document.createElement("span");
          label.textContent = "任务定时：";
          const strong = document.createElement("strong");
          strong.textContent = when;
          label.append(strong);
          meta.append(label);
          const status = document.createElement("span");
          status.className = "schedule-status";
          status.textContent = "上次构建结果：" + statusText(item.last_status);
          const del = document.createElement("button");
          del.className = "schedule-delete";
          del.textContent = "删除";
          del.onclick = async (e) => {
            e.stopPropagation();
            if (confirm("确定删除任务？")) {
              await fetch("/api/scheduler-tasks/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id: item.id }),
              });
              await refresh();
            }
          };
          card.append(name, meta, status, del);
          card.onclick = () => {
            window.__selectedTaskId = item.id;
            const type = item.scheduler_type || item.dispatcher;
            const page =
              type === "test_scheduler"
                ? "test-scheduler"
                : type === "code_review_scheduler" ||
                    item.tool_id === "code-review-agent"
                  ? "code-review"
                  : null;
            if (page) load(page);
            else alert("不支持的任务类型：" + type);
          };
          other.append(card);
        });
      }
    } catch (e) {
      list.textContent = "加载失败：" + e.message;
    }
  }
  document.getElementById("schedule-add").onclick = async () => {
    const box = document.getElementById("schedule-create"),
      sel = document.getElementById("schedule-type");
    box.hidden = false;
    let d;
    try {
      d = await fetch("/api/scheduler-tasks/types", { cache: "no-store" }).then(
        (r) => r.json(),
      );
    } catch (e) {
      d = { types: [] };
    }
    if (!d.types || !d.types.length)
      d = {
        types: [
          { scheduler_type: "test_scheduler", name: "测试任务" },
          { scheduler_type: "code_review_scheduler", name: "代码检查器" },
        ],
      };
    sel.replaceChildren(
      ...d.types.map((x) => {
        const o = document.createElement("option");
        o.value = x.scheduler_type;
        o.textContent = x.name;
        return o;
      }),
    );
  };
  document.getElementById("schedule-cancel").onclick = () =>
    (document.getElementById("schedule-create").hidden = true);
  document.getElementById("schedule-save").onclick = async () => {
    const m = document.getElementById("schedule-create-msg");
    const b = await fetch("/api/scheduler-tasks/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scheduler_type: document.getElementById("schedule-type").value,
        name: document.getElementById("schedule-name").value,
        run_time: document.getElementById("schedule-time").value,
        run_type: 1,
        param: {},
      }),
    }).then((r) => r.json());
    m.textContent = b.ok ? "创建成功" : (b.error || "创建失败");
    if (b.ok) {
      document.getElementById("schedule-create").hidden = true;
      await refresh();
    }
  };
  await refresh(false);
  setInterval(() => refresh(true), 3000);
  document.getElementById("scheduler-start").onclick = async () => {
    await fetch("/api/scheduler/start", { method: "POST" });
    msg.textContent = "启动请求已发送";
    await refresh();
  };
  document.getElementById("scheduler-stop").onclick = async () => {
    await fetch("/api/scheduler/stop", { method: "POST" });
    msg.textContent = "关闭请求已发送";
    await refresh();
  };
}
export async function mount() {
  scope = createPageScope();
  await initScheduler();
}
export function unmount() {
  scope?.dispose();
}
