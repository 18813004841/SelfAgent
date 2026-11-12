import { load } from "../app.js";
import { createPageScope } from "../shared/page-scope.js";
import { formatReviewLogData } from "../shared/review-log.js";
let scope;
const fetch = (...args) => scope.fetch(...args);
const setInterval = (...args) => scope.setInterval(...args);
async function initCodeReview() {
  const taskId = window.__selectedTaskId || "code-review-daily";
  window.__selectedTaskId = taskId;
  const msg = document.getElementById("review-config-msg"),
    log = document.getElementById("review-log");
  if (window.__schedulerTimer) clearInterval(window.__schedulerTimer);
  let skillsLoaded = false,
    extraLoaded = false;
  let lastLogText = null;
  let pendingLogText = null;
  function flushPendingLog() {
    const selection = window.getSelection();
    const selectingLog =
      selection &&
      selection.type === "Range" &&
      !selection.isCollapsed &&
      log.contains(selection.anchorNode) &&
      log.contains(selection.focusNode);
    if (!selectingLog && pendingLogText !== null) {
      log.textContent = pendingLogText;
      lastLogText = pendingLogText;
      pendingLogText = null;
    }
  }
  document.addEventListener("selectionchange", flushPendingLog);
  const skills =
    document.getElementById("review-skill-paths") ||
    document.createElement("div");
  function addSkill(path = "") {
    const row = document.createElement("div");
    row.className = "review-skill-row";
    const input = document.createElement("input");
    input.value = path;
    input.placeholder = "Skill 目录";
    const choose = document.createElement("button");
    choose.type = "button";
    choose.textContent = "选择目录";
    choose.onclick = async () => {
      try {
        const r = await fetch("/api/scheduler-tasks/code-review/choose", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            current_path: document
              .getElementById("review-project-path")
              .value.trim(),
          }),
        });
        const d = await r.json();
        if (!r.ok || !d.ok) throw Error(d.error || "目录选择失败");
        if (d.project_path) input.value = d.project_path;
      } catch (e) {
        alert(e.message);
      }
    };
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "删除";
    remove.onclick = () => row.remove();
    row.append(input, choose, remove);
    skills.append(row);
  }
  const skillAdd = document.getElementById("review-skill-add");
  if (skillAdd) skillAdd.onclick = () => addSkill();
  function render(x) {
    const extra = document.getElementById("review-extra-rules");
    if (!extraLoaded && extra) {
      extra.checked = !!x.allow_extra_rules;
      const threshold = document.getElementById("review-failure-threshold");
      if (threshold) threshold.value = x.failure_threshold || "high";
      extraLoaded = true;
    }
    if (!skillsLoaded) {
      const paths = Array.isArray(x.skill_paths)
        ? x.skill_paths
        : [x.skill_paths || "skills"];
      paths.forEach(addSkill);
      skillsLoaded = true;
    }
    const result = document.getElementById("review-result");
    const status = x.last_status || "未执行";
    result.textContent =
      "执行结果：" +
      ({
        succeeded: "成功",
        success: "成功",
        failed: "失败",
        running: "执行中",
        cancelled: "已取消",
        cancelling: "取消中",
      }[status] || status);
    result.className =
      "review-result " +
      (status === "succeeded" || status === "success"
        ? "success"
        : status === "failed"
          ? "failed"
          : status === "running"
            ? "running"
            : "");
    if (Object.prototype.hasOwnProperty.call(x, "project_path")) {
      document.getElementById("review-time").textContent =
        "每天 " + (x.run_at || "04:00");
      if (document.activeElement.id !== "review-project-path")
        document.getElementById("review-project-path").value =
          x.project_path || "未配置";
      if (document.activeElement.id !== "review-branch")
        document.getElementById("review-branch").value = x.branch || "未配置";
    }
    const events = ((x.log && x.log.events) || [])
      .map(
        (e) =>
          `[${e.time}] ${e.kind === "execute" ? "执行任务" : e.kind === "progress" ? "进度更新" : "执行结果"} ${e.message}${e.data && Object.keys(e.data).length ? "\n" + JSON.stringify(e.data, formatReviewLogData, 2) : ""}`,
      )
      .join("\n");
    const nextLogText = events || "本次还没有执行日志";
    // 轮询时只有日志真正变化才改写 DOM，避免打断用户选中文本。
    if (lastLogText !== nextLogText) {
      const selection = window.getSelection();
      const selectingLog =
        selection &&
        selection.rangeCount > 0 &&
        log.contains(selection.anchorNode);
      if (!selectingLog) {
        log.textContent = nextLogText;
        lastLogText = nextLogText;
      } else {
        pendingLogText = nextLogText;
      }
    }
  }
  async function refresh(statusOnly = false) {
    const d = await fetch(
      "/api/scheduler-tasks/code-review/" +
        encodeURIComponent(taskId) +
        (statusOnly ? "?refresh=status" : ""),
      { cache: "no-store" },
    ).then((r) => r.json());
    if (!d.ok || !d.task) throw Error(d.error || "配置读取失败");
    render(d.task);
  }
  document.getElementById("back-scheduler").onclick = () => load("scheduler");
  document.getElementById("review-choose").onclick = async () => {
    msg.textContent = "正在打开目录选择窗口...";
    try {
      const body = await fetch("/api/scheduler-tasks/code-review/choose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }).then((r) => r.json());
      if (body.project_path) {
        document.getElementById("review-project-path").value =
          body.project_path;
        msg.textContent = "已选择目录，请写入配置";
      } else {
        msg.textContent = "未选择目录";
      }
    } catch (e) {
      msg.textContent = "选择目录失败：" + e.message;
    }
  };
  document.getElementById("review-save").onclick = async () => {
    const d = await fetch("/api/scheduler-tasks/code-review/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_path: document
          .getElementById("review-project-path")
          .value.trim(),
        branch: document.getElementById("review-branch").value.trim(),
        skill_paths: [...skills.querySelectorAll("input")]
          .map((e) => e.value.trim())
          .filter(Boolean),
        allow_extra_rules: !!(
          document.getElementById("review-extra-rules") &&
          document.getElementById("review-extra-rules").checked
        ),
        failure_threshold:
          (document.getElementById("review-failure-threshold") &&
            document.getElementById("review-failure-threshold").value) ||
          "high",
        schedule_id: taskId,
      }),
    }).then((r) => r.json());
    msg.textContent = d.ok ? "配置已写入" : "写入失败";
    if (d.task) render(d.task);
  };
  const stopButton = document.getElementById("review-stop");
  if (stopButton)
    stopButton.onclick = async () => {
      msg.hidden = false;
      msg.textContent = "正在终止...";
      try {
        const d = await fetch("/api/scheduler-tasks/code-review/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ schedule_id: taskId }),
        }).then((r) => r.json());
        msg.textContent = d.ok ? "终止请求已发送" : "终止失败";
        if (d.task) render(d.task);
      } catch (e) {
        msg.textContent = "终止失败：" + e.message;
      }
    };
  const runButton = document.getElementById("review-run");
  if (runButton)
    runButton.onclick = async () => {
      msg.hidden = false;
      msg.textContent = "正在执行...";
      runButton.disabled = true;
      try {
        const response = await fetch("/api/scheduler-tasks/code-review/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_path: document
              .getElementById("review-project-path")
              .value.trim(),
            branch: document.getElementById("review-branch").value.trim(),
            skill_paths: [...skills.querySelectorAll("input")]
              .map((e) => e.value.trim())
              .filter(Boolean),
            allow_extra_rules: !!(
              document.getElementById("review-extra-rules") &&
              document.getElementById("review-extra-rules").checked
            ),
            failure_threshold:
              (document.getElementById("review-failure-threshold") &&
                document.getElementById("review-failure-threshold").value) ||
              "high",
            schedule_id: taskId,
          }),
        });
        const d = await response.json();
        if (!response.ok || !d.ok)
          throw Error(d.error || d.message || "执行失败");
        msg.textContent = "执行已开始";
        if (d.task) render(d.task);
      } catch (e) {
        msg.textContent = "执行失败：" + e.message;
        log.textContent += "\n" + msg.textContent;
      } finally {
        runButton.disabled = false;
      }
    };
  await refresh().catch((e) => {
    log.textContent = "配置读取失败：" + e.message;
  });
  if (window.__codeReviewTimer) clearInterval(window.__codeReviewTimer);
  window.__codeReviewTimer = setInterval(() => {
    if (!document.getElementById("review-log")) {
      clearInterval(window.__codeReviewTimer);
      return;
    }
    if (!document.hidden)
      refresh(true).catch((e) => {
        log.textContent = "状态读取失败：" + e.message;
      });
  }, 2000);
}
export async function mount() {
  scope = createPageScope();
  await initCodeReview();
}
export function unmount() {
  document.removeEventListener("selectionchange", flushPendingLog);
  scope?.dispose();
}
