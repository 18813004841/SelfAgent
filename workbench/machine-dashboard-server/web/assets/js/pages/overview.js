import { createPageScope } from "../shared/page-scope.js";
let scope;
async function refresh() {
  const error = document.querySelector("#overview-error");
  try {
    const response = await scope.fetch("/api/machines", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const machine = data.machines?.[0];
    if (!machine) throw new Error("没有本机数据");
    document.querySelector("#hostname").textContent = machine.hostname;
    document.querySelector("#system").textContent = machine.os;
    const metricsResponse = await scope.fetch(
      `/api/machine/${encodeURIComponent(machine.machine_id)}/metrics`,
      { cache: "no-store" },
    );
    if (!metricsResponse.ok) throw new Error(`HTTP ${metricsResponse.status}`);
    const { metrics } = await metricsResponse.json();
    document.querySelector("#memory").textContent =
      metrics.memory?.percent != null ? `${metrics.memory.percent}%` : "-";
    document.querySelector("#disk").textContent =
      (metrics.disks || []).map((x) => `${x.mount} ${x.percent}%`).join("、") ||
      "-";
    document.querySelector("#ip").textContent =
      (metrics.ips || []).join("、") || "-";
    error.textContent = "";
  } catch (e) {
    error.textContent = `加载失败：${e.message}`;
  }
}
export async function mount() {
  scope = createPageScope();
  document.querySelector("#overview-refresh").onclick = refresh;
  await refresh();
}
export function unmount() {
  scope?.dispose();
}
