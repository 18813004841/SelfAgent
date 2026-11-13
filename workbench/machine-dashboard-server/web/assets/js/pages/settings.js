import { load } from "../app.js";
import { createPageScope } from "../shared/page-scope.js";
let scope;
const fetch = (...args) => scope.fetch(...args);
const setInterval = (...args) => scope.setInterval(...args);
async function initSettings() {
  const input = document.getElementById("storage"),
    msg = document.getElementById("msg");
  async function loadStorage() {
    try {
      const r = await fetch("/api/settings/storage");
      const d = await r.json();
      if (!r.ok || !d.ok) throw Error(d.error || "加载失败");
      input.value = d.settings.storage_dir || d.default;
      msg.textContent = "已加载当前保存路径";
    } catch (e) {
      msg.textContent = "加载失败：" + e.message;
    }
  }
  document.getElementById("load-storage").onclick = async () => {
    msg.textContent = "正在打开目录选择窗口...";
    const r = await fetch("/api/settings/storage/choose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const d = await r.json();
    if (!r.ok || !d.ok) throw Error(d.error || "目录选择失败");
    input.value = d.settings.storage_dir;
    msg.textContent = d.selected ? "已更新保存目录" : "未选择目录";
  };
  await loadStorage();
}
export async function mount() {
  scope = createPageScope();
  await initSettings();
}
export function unmount() {
  scope?.dispose();
}
